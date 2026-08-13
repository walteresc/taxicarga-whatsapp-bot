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
from apps.integrations.services.channel_policy import is_feature_enabled
from apps.integrations.services.human_takeover import (
    apply_chatwoot_human_takeover,
)
from apps.integrations.errors import InvalidTransition, PendingHumanOutbox
from apps.integrations.services.attention_control import (
    ATTRIBUTE_AGENT,
    ATTRIBUTE_BOT,
    ATTRIBUTE_KEY,
    apply_chatwoot_return_request,
    reflect_attention_control,
)
from apps.integrations.providers.chatwoot.exceptions import ChatwootError


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


def _conversation_updated_payload(payload):
    """Resolve Chatwoot 4.16 conversation_updated data without guessing an actor."""
    if str(payload.get("event") or "") != "conversation_updated":
        return {}
    conversation = payload.get("conversation")
    return conversation if isinstance(conversation, dict) else payload


def _event_refs(payload):
    conversation = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else {}
    if not conversation:
        conversation = _conversation_updated_payload(payload)
    account_id = _object_id(payload.get("account") or payload.get("account_id"))
    conversation_id = _object_id(conversation.get("id") or payload.get("conversation_id"))
    inbox_id = _object_id(
        payload.get("inbox") or payload.get("inbox_id") or conversation.get("inbox_id") or conversation.get("inbox")
    )
    message_id = _object_id(payload.get("id"))
    return account_id, inbox_id, conversation_id, message_id


def _attention_control_change(payload):
    """Return (before, after) only for an explicit custom-attribute change."""
    changes = payload.get("changed_attributes")
    if not isinstance(changes, list):
        return "", ""
    for change in changes:
        if not isinstance(change, dict):
            continue
        custom_change = change.get("custom_attributes")
        if not isinstance(custom_change, dict):
            continue
        previous = custom_change.get("previous_value")
        current = custom_change.get("current_value")
        if isinstance(previous, dict) and isinstance(current, dict):
            return str(previous.get(ATTRIBUTE_KEY) or ""), str(current.get(ATTRIBUTE_KEY) or "")
    return "", ""


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
    # Customer incoming message (only if mapping exists and sender is contact)
    message_type = payload.get("message_type")
    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
    sender_type = str(sender.get("type", "")).lower()
    if mapping and message_type in (0, "0", "incoming") and sender_type == "contact":
        return "incoming_customer"
    return "unsupported"


def _safe_payload(payload, refs, classification):
    account_id, inbox_id, conversation_id, message_id = refs
    sender = payload.get("sender")
    conversation = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else {}
    custom_attributes = conversation.get("custom_attributes")
    if not isinstance(custom_attributes, dict):
        custom_attributes = payload.get("custom_attributes") if isinstance(payload.get("custom_attributes"), dict) else {}
    performer = payload.get("performer") if isinstance(payload.get("performer"), dict) else {}
    attention_before, attention_after = _attention_control_change(payload)
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
        "attention_control": str(custom_attributes.get(ATTRIBUTE_KEY) or ""),
        "performer_id": _object_id(performer.get("id")),
        "performer_type": str(performer.get("type") or ""),
        "actor_source": "chatwoot",
        "actor_identity": _object_id(performer.get("id")) or "unknown",
        "attention_control_before": attention_before,
        "attention_control_after": attention_after,
    }


def _process_incoming_customer_message(mapping, payload, account_id, message_id):
    """Process customer incoming from Chatwoot webhook.

    Create MensajeWhatsApp + BotGeneration if not already present.
    """
    from apps.integrations.models import BotGeneration, ExternalMessageMapping
    from apps.integrations.services.bot_generation_worker import queue_bot_generation
    from apps.whatsapp.models import MensajeWhatsApp
    from apps.integrations.enums import GenerationStatus, OwnerState

    try:
        # Check if message already mapped
        msg_mapping = ExternalMessageMapping.objects.filter(
            provider=Provider.CHATWOOT,
            external_id=message_id,
        ).first()

        if msg_mapping and msg_mapping.internal_message_id:
            # Message already in our system
            message = MensajeWhatsApp.objects.get(pk=msg_mapping.internal_message_id)
            action = "already_mapped"
        else:
            # Create MensajeWhatsApp for this customer inbound
            message = MensajeWhatsApp.objects.create(
                conversacion=mapping.conversation,
                meta_message_id=f"chatwoot:{message_id}",  # Synthetic ID
                direccion=MensajeWhatsApp.ENTRANTE,
                origen=MensajeWhatsApp.ORIGEN_CLIENTE,
                tipo="texto",
                contenido=str(payload.get("content") or ""),
                estado="recibido",
            )
            # Map Chatwoot message to our MensajeWhatsApp
            ExternalMessageMapping.objects.get_or_create(
                provider=Provider.CHATWOOT,
                external_id=message_id,
                defaults={"internal_message_id": message.id},
            )
            action = "message_created"

        # Ensure BotGeneration exists
        existing_gen = BotGeneration.objects.filter(
            input_message_id=message.id
        ).first()

        if not existing_gen:
            generation = BotGeneration.objects.create(
                conversation_id=mapping.conversation.id,
                status=GenerationStatus.GENERATING,
                request_key=f"chatwoot-incoming-{message_id}",
                control_version_started=0,
                expected_owner_state=OwnerState.BOT_ACTIVE,
            )
            try:
                queue_bot_generation(
                    message_id=message.id,
                    generation_id=generation.id,
                )
                action = "queued_for_bot"
            except Exception:
                pass

        return action
    except Exception:
        return "error"


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


def process_webhook(payload, delivery_id, *, chatwoot_client=None):
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
    elif event_type == "conversation_updated":
        known_inbox = ChannelInboxMapping.objects.filter(
            active=True, account__active=True, account__account_id=account_id, inbox_id=inbox_id,
        ).exists()
        classification = (
            "wrong_account" if account_id != str(settings.CHATWOOT_ACCOUNT_ID)
            else "wrong_inbox" if not known_inbox
            else "unmapped_conversation" if mapping is None
            else "attention_control"
        )
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
    if classification == "django_projection":
        # django_projection can be: (1) Customer inbound that Django already processed,
        # or (2) Bot outbound that Django created and projected to Chatwoot.
        # Use message_type to distinguish:
        # - message_type 0 = incoming (customer message — might need BotGeneration)
        # - message_type 1 = outgoing (bot response — truly ignore)

        message_type = payload.get("message_type")
        if message_type in (1, "1", "outgoing"):
            # This is bot outbound that Django already handled; truly ignore
            action = "ignored"
        else:
            # Either incoming (customer) or ambiguous; try to process
            from apps.integrations.models import BotGeneration
            from apps.integrations.services.bot_generation_worker import queue_bot_generation
            from apps.whatsapp.models import MensajeWhatsApp

            try:
                from apps.integrations.enums import GenerationStatus, OwnerState

                msg_mapping = ExternalMessageMapping.objects.filter(
                    provider=Provider.CHATWOOT,
                    external_id=message_id,
                ).first()

                if msg_mapping and msg_mapping.internal_message_id:
                    message = MensajeWhatsApp.objects.get(pk=msg_mapping.internal_message_id)
                    # Ensure BotGeneration exists for this message
                    existing_gen = BotGeneration.objects.filter(
                        input_message_id=message.id
                    ).first()
                    if not existing_gen and message.direccion == "ENTRANTE":
                        # No BotGeneration yet - create one
                        generation = BotGeneration.objects.create(
                            conversation_id=mapping.conversation.id,
                            status=GenerationStatus.GENERATING,
                            request_key=f"chatwoot-recovery-{message_id}",
                            control_version_started=0,
                            expected_owner_state=OwnerState.BOT_ACTIVE,
                        )
                        try:
                            queue_bot_generation(
                                message_id=message.id,
                                generation_id=generation.id,
                            )
                            action = "queued_for_bot"
                        except Exception:
                            pass
            except (MensajeWhatsApp.DoesNotExist, ExternalMessageMapping.DoesNotExist, AttributeError):
                pass

            action = "ignored" if action == "ignored" else action
    elif classification == "human_agent":
        if (
            is_feature_enabled(mapping.conversation.channel, "human_takeover")
        ):
            takeover = apply_chatwoot_human_takeover(
                mapping_id=mapping.id,
                payload=payload,
                account_id=account_id,
                inbox_id=inbox_id,
                message_id=message_id,
            )
            message_created = takeover.message_created
            try:
                reflect_attention_control(mapping, ATTRIBUTE_AGENT, client=chatwoot_client)
            except ChatwootError:
                pass
        else:
            _message, message_created = _create_human_message(mapping, payload, account_id, message_id)
        action = "normalized" if message_created else "ignored"
    elif classification == "attention_control":
        conversation_payload = _conversation_updated_payload(payload)
        custom_attributes = conversation_payload.get("custom_attributes")
        if not isinstance(custom_attributes, dict):
            custom_attributes = payload.get("custom_attributes") if isinstance(payload.get("custom_attributes"), dict) else {}
        previous, requested = _attention_control_change(payload)
        if previous == ATTRIBUTE_AGENT and requested == ATTRIBUTE_BOT:
            try:
                _control, result = apply_chatwoot_return_request(
                    mapping=mapping, payload=payload, account_id=account_id, inbox_id=inbox_id,
                    delivery_id=external_event_id, client=chatwoot_client,
                )
                action = "returned_to_bot" if result.changed else "ignored"
            except PendingHumanOutbox:
                try:
                    reflect_attention_control(mapping, ATTRIBUTE_AGENT, client=chatwoot_client)
                except ChatwootError:
                    pass
                action = "return_blocked_pending_human_outbox"
            except InvalidTransition:
                action = "ignored"
        else:
            action = "ignored"
    elif classification == "incoming_customer":
        # Customer message from Chatwoot (not django_projection)
        # Likely Meta → Chatwoot → Django flow
        if mapping and mapping.conversation:
            action = _process_incoming_customer_message(
                mapping, payload, account_id, message_id
            )
        else:
            action = "ignored"

    inbox_event.status = InboxStatus.PROCESSED if action in {
        "normalized", "returned_to_bot", "return_blocked_pending_human_outbox",
        "queued_for_bot", "message_created", "already_mapped"
    } else InboxStatus.IGNORED
    inbox_event.processed_at = timezone.now()
    inbox_event.save(update_fields=["status", "processed_at"])
    return WebhookResult(classification, action)
