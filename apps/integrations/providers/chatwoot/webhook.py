import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.integrations.enums import (
    AuthorType,
    ContentType,
    Direction,
    InboxStatus,
    Provider,
    Visibility,
)
from apps.integrations.errors import IdempotencyConflict
from apps.integrations.models import (
    ChannelInboxMapping,
    ConversationMapping,
    ExternalMessageMapping,
    IntegrationMessage,
)
from apps.integrations.services.inbox_outbox import register_inbox_event
from apps.integrations.services.human_takeover import (
    apply_chatwoot_human_takeover,
    channel_is_stage7_scoped,
)


class InvalidWebhookSignature(ValueError):
    pass


class InvalidWebhookPayload(ValueError):
    pass


@dataclass(frozen=True)
class WebhookResult:
    classification: str
    action: str
    duplicate: bool = False


def verify_signature(raw_body, timestamp_header, signature_header, *, now=None):
    secret = settings.CHATWOOT_WEBHOOK_SECRET
    if not secret:
        raise InvalidWebhookSignature("Webhook secret is not configured.")
    try:
        timestamp = int(timestamp_header)
    except (TypeError, ValueError) as exc:
        raise InvalidWebhookSignature("Invalid webhook timestamp.") from exc
    current = int(time.time() if now is None else now)
    if abs(current - timestamp) > settings.CHATWOOT_WEBHOOK_MAX_AGE_SECONDS:
        raise InvalidWebhookSignature("Webhook timestamp is outside the accepted window.")
    if not isinstance(signature_header, str) or not signature_header.startswith("sha256="):
        raise InvalidWebhookSignature("Invalid webhook signature format.")
    supplied = signature_header[7:]
    if len(supplied) != 64:
        raise InvalidWebhookSignature("Invalid webhook signature format.")
    try:
        bytes.fromhex(supplied)
    except ValueError as exc:
        raise InvalidWebhookSignature("Invalid webhook signature format.") from exc
    signed = str(timestamp).encode("ascii") + b"." + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied.lower(), expected):
        raise InvalidWebhookSignature("Webhook signature mismatch.")


def parse_payload(raw_body):
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidWebhookPayload("Invalid JSON payload.") from exc
    if not isinstance(payload, dict):
        raise InvalidWebhookPayload("Webhook payload must be an object.")
    return payload


def _object_id(value):
    if isinstance(value, dict):
        value = value.get("id")
    return "" if value is None else str(value)


def _event_refs(payload):
    conversation = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else {}
    account_id = _object_id(payload.get("account") or payload.get("account_id"))
    conversation_id = _object_id(conversation.get("id") or payload.get("conversation_id"))
    inbox_id = _object_id(
        payload.get("inbox") or payload.get("inbox_id") or conversation.get("inbox_id") or conversation.get("inbox")
    )
    message_id = _object_id(payload.get("id"))
    return account_id, inbox_id, conversation_id, message_id


def _is_projection(payload, account_id, message_id):
    if ExternalMessageMapping.objects.filter(
        provider=Provider.CHATWOOT,
        account_scope=account_id,
        external_id=message_id,
    ).exists():
        return True
    attributes = payload.get("content_attributes")
    return isinstance(attributes, dict) and attributes.get("taxicarga_origin") == "django_projection"


def _is_human_agent(payload):
    sender = payload.get("sender")
    sender_type = sender.get("type", "") if isinstance(sender, dict) else ""
    message_type = payload.get("message_type")
    return str(sender_type).lower() == "user" and message_type in (1, "1", "outgoing")


def _classify(payload, account_id, inbox_id, message_id, mapping):
    if account_id != str(settings.CHATWOOT_ACCOUNT_ID):
        return "wrong_account"
    known_inbox = ChannelInboxMapping.objects.filter(
        active=True,
        account__active=True,
        account__account_id=account_id,
        inbox_id=inbox_id,
    ).exists()
    if not known_inbox:
        return "wrong_inbox"
    if payload.get("private") is True:
        return "private_note"
    if _is_projection(payload, account_id, message_id):
        return "django_projection"
    if mapping is None:
        return "unmapped_conversation"
    if _is_human_agent(payload):
        return "human_agent"
    return "unsupported"


def _safe_payload(payload, refs, classification):
    account_id, inbox_id, conversation_id, message_id = refs
    sender = payload.get("sender")
    return {
        "event": str(payload.get("event", "")),
        "message_id": message_id,
        "conversation_id": conversation_id,
        "account_id": account_id,
        "inbox_id": inbox_id,
        "private": payload.get("private") is True,
        "sender_id": _object_id(sender.get("id")) if isinstance(sender, dict) else "",
        "sender_type": str(sender.get("type", "")) if isinstance(sender, dict) else "",
        "classification": classification,
    }


def _create_human_message(mapping, payload, account_id, message_id):
    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
    data = {
        "conversation": mapping.conversation,
        "provider": Provider.CHATWOOT,
        "external_scope": account_id,
        "channel": mapping.conversation.channel,
        "external_message_id": message_id,
        "direction": Direction.OUTBOUND,
        "author_type": AuthorType.AGENT,
        "visibility": Visibility.PUBLIC,
        "content_type": ContentType.TEXT,
        "text": str(payload.get("content") or ""),
        "metadata": {
            "source": "chatwoot_webhook",
            "external_sender_id": _object_id(sender.get("id")),
        },
        "idempotency_key": f"message_created:{message_id}",
    }
    try:
        with transaction.atomic():
            return IntegrationMessage.objects.create(**data), True
    except IntegrityError:
        message = IntegrationMessage.objects.filter(
            provider=Provider.CHATWOOT,
            external_scope=account_id,
            external_message_id=message_id,
        ).first()
        if message:
            return message, False
        raise


@transaction.atomic
def process_webhook(payload, delivery_id):
    refs = _event_refs(payload)
    account_id, inbox_id, conversation_id, message_id = refs
    event_type = str(payload.get("event") or "")
    if event_type == "message_created" and not message_id:
        raise InvalidWebhookPayload("message_created requires a message id.")

    mapping = None
    if account_id == str(settings.CHATWOOT_ACCOUNT_ID):
        mapping = ConversationMapping.objects.select_related("conversation__channel").filter(
            active=True,
            external_conversation_id=conversation_id,
            contact_inbox__inbox__account__account_id=account_id,
            contact_inbox__inbox__inbox_id=inbox_id,
        ).first()

    classification = "unsupported"
    if event_type == "message_created":
        classification = _classify(payload, account_id, inbox_id, message_id, mapping)
    safe = _safe_payload(payload, refs, classification)
    scope = account_id or "unknown"
    fallback = "fallback:" + hashlib.sha256(json.dumps(safe, sort_keys=True).encode()).hexdigest()
    external_event_id = delivery_id or fallback
    idempotency_key = f"message_created:{message_id}" if event_type == "message_created" else f"{event_type}:{external_event_id}"
    try:
        inbox_event, created = register_inbox_event(
            provider=Provider.CHATWOOT,
            external_scope=scope,
            external_event_id=external_event_id,
            event_type=event_type or "unknown",
            idempotency_key=idempotency_key,
            safe_payload=safe,
            account_ref=account_id,
            inbox_ref=inbox_id,
            channel=mapping.conversation.channel if mapping else None,
            conversation=mapping.conversation if mapping else None,
        )
    except IdempotencyConflict:
        raise InvalidWebhookPayload("Conflicting webhook idempotency key.")
    if not created:
        return WebhookResult(classification, "ignored", duplicate=True)

    action = "ignored"
    if classification == "human_agent":
        if (
            settings.CHATWOOT_HUMAN_TAKEOVER_ENABLED
            and channel_is_stage7_scoped(mapping.conversation.channel_id)
        ):
            takeover = apply_chatwoot_human_takeover(
                mapping_id=mapping.id,
                payload=payload,
                account_id=account_id,
                inbox_id=inbox_id,
                message_id=message_id,
            )
            message_created = takeover.message_created
        else:
            _message, message_created = _create_human_message(mapping, payload, account_id, message_id)
        action = "normalized" if message_created else "ignored"
    inbox_event.status = InboxStatus.PROCESSED if action == "normalized" else InboxStatus.IGNORED
    inbox_event.processed_at = timezone.now()
    inbox_event.save(update_fields=["status", "processed_at"])
    return WebhookResult(classification, action)
