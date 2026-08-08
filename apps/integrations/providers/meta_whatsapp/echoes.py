import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel

from ...enums import AuthorType, Direction, GenerationStatus, OutboxStatus, OwnerState, Provider, Visibility
from ...errors import InvalidTransition, PrivateMessageBlocked, UnknownChannel
from ...models import (
    BotGeneration,
    ConversationControl,
    ConversationTransitionAudit,
    ExternalMessageMapping,
    IntegrationInboxEvent,
    IntegrationMessage,
    IntegrationOutboxEvent,
)
from ...services.inbox_outbox import register_inbox_event


@dataclass(frozen=True)
class SmbEchoResult:
    message: IntegrationMessage
    inbox_event: IntegrationInboxEvent
    transitioned: bool
    duplicate: bool


def process_smb_message_echoes(payload):
    results = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "smb_message_echoes":
                continue
            value = change.get("value") or {}
            phone_number_id = str((value.get("metadata") or {}).get("phone_number_id") or "")
            for echo in value.get("message_echoes") or value.get("smb_message_echoes") or []:
                normalized_echo = dict(echo)
                normalized_echo.setdefault("phone_number_id", phone_number_id)
                results.append(process_smb_message_echo(normalized_echo))
    return results


def process_smb_message_echo(echo):
    parsed = _parse_echo(echo)
    if parsed["visibility"] != Visibility.PUBLIC:
        raise PrivateMessageBlocked("Private echoes cannot be processed as customer-visible messages.")
    channel = WhatsAppChannel.objects.filter(phone_number_id=parsed["phone_number_id"], activo=True).first()
    if not channel:
        raise UnknownChannel("Echo belongs to an unknown or inactive channel.")
    conversation = _resolve_conversation(channel, parsed["customer_phone"])
    owner_state = ConversationControl.objects.get(conversation=conversation).owner_state
    if owner_state not in {OwnerState.BOT_ACTIVE, OwnerState.WAITING_AGENT, OwnerState.AGENT_ACTIVE}:
        raise InvalidTransition("External human echo is not allowed in current state.")
    safe_payload = {
        "message_id": parsed["message_id"],
        "phone_number_id": parsed["phone_number_id"],
        "content_type": parsed["content_type"],
        "text": parsed["text"],
        "source": "whatsapp_business_app",
    }
    inbox_event, created = register_inbox_event(
        provider=Provider.META_WHATSAPP,
        external_scope=parsed["phone_number_id"],
        event_type="smb_message_echo",
        idempotency_key=f"smb-echo:{parsed['phone_number_id']}:{parsed['message_id']}",
        safe_payload=safe_payload,
        external_event_id=parsed["message_id"],
        channel=channel,
        conversation=conversation,
        correlation_id=parsed["correlation_id"],
    )
    existing = IntegrationMessage.objects.filter(
        provider=Provider.META_WHATSAPP, external_scope=parsed["phone_number_id"], external_message_id=parsed["message_id"]
    ).first()
    if existing:
        return SmbEchoResult(existing, inbox_event, False, True)
    with transaction.atomic():
        control = ConversationControl.objects.select_for_update().get(conversation=conversation)
        existing = IntegrationMessage.objects.select_for_update().filter(
            provider=Provider.META_WHATSAPP, external_scope=parsed["phone_number_id"], external_message_id=parsed["message_id"]
        ).first()
        if existing:
            return SmbEchoResult(existing, inbox_event, False, True)
        message = IntegrationMessage.objects.create(
            conversation=conversation,
            provider=Provider.META_WHATSAPP,
            external_scope=parsed["phone_number_id"],
            channel=channel,
            external_message_id=parsed["message_id"],
            direction=Direction.OUTBOUND,
            author_type=AuthorType.EXTERNAL_HUMAN,
            visibility=Visibility.PUBLIC,
            content_type=parsed["content_type"],
            text=parsed["text"],
            metadata={"source": "whatsapp_business_app", "echo": True, "linked_device": True, "phone_number_id": parsed["phone_number_id"]},
            idempotency_key=f"meta-whatsapp:{parsed['phone_number_id']}:{parsed['message_id']}",
            correlation_id=parsed["correlation_id"],
            external_timestamp=parsed["timestamp"],
        )
        ExternalMessageMapping.objects.get_or_create(
            provider=Provider.META_WHATSAPP,
            account_scope=parsed["phone_number_id"],
            external_id=parsed["message_id"],
            defaults={"logical_message": message},
        )
        before = control.owner_state
        version_before = control.control_version
        transitioned = control.owner_state != OwnerState.AGENT_ACTIVE
        if transitioned:
            control.owner_state = OwnerState.AGENT_ACTIVE
            control.control_version += 1
            control.active_advisor = None
            control.taken_at = timezone.now()
            control.last_reason = "external_human_echo"
            control.last_actor = None
            control.last_actor_type = "external_human"
            control.last_correlation_id = parsed["correlation_id"]
            control.save()
        BotGeneration.objects.filter(
            conversation=conversation,
            status__in=[GenerationStatus.PENDING, GenerationStatus.GENERATING, GenerationStatus.READY],
        ).update(
            status=GenerationStatus.CANCELLED,
            cancelled_at=timezone.now(),
            cancel_reason="external_human_echo",
        )
        ConversationTransitionAudit.objects.create(
                conversation=conversation,
                from_state=before,
                to_state=control.owner_state,
                action="external_human_takeover" if transitioned else "external_human_message",
                actor=None,
                actor_type="external_human",
                external_actor_ref="",
                source="whatsapp_business_app",
                version_before=version_before,
                version_after=control.control_version,
                reason="smb_message_echo",
                idempotency_key=f"smb-audit:{parsed['message_id']}",
                correlation_id=parsed["correlation_id"],
                metadata={"advisor_identity_verified": False},
        )
        IntegrationOutboxEvent.objects.get_or_create(
            destination=Provider.CHATWOOT,
            destination_scope=parsed["phone_number_id"],
            idempotency_key=f"chatwoot-reflect-smb:{message.id}",
            defaults={
                "event_type": "reflect_external_human_message",
                "logical_message": message,
                "conversation": conversation,
                "safe_payload": {"logical_message_id": str(message.id), "source": "whatsapp_business_app"},
                "status": OutboxStatus.PENDING,
                "correlation_id": parsed["correlation_id"],
            },
        )
        inbox_event.status = "processed"
        inbox_event.processed_at = timezone.now()
        inbox_event.save(update_fields=["status", "processed_at"])
        return SmbEchoResult(message, inbox_event, transitioned, not created)


def _resolve_conversation(channel, customer_phone):
    cliente = Cliente.objects.filter(telefono=customer_phone).first()
    if not cliente:
        raise UnknownChannel("Echo customer does not have a known conversation.")
    conversation = ConversacionWhatsApp.objects.filter(
        cliente=cliente, channel=channel
    ).exclude(estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA).order_by("-ultima_actividad").first()
    if not conversation:
        raise UnknownChannel("Echo does not map to an active channel conversation.")
    return conversation


def _parse_echo(echo):
    if not isinstance(echo, dict):
        raise ValueError("Invalid smb echo payload.")
    message_id = str(echo.get("id") or "").strip()
    phone_number_id = str(echo.get("phone_number_id") or "").strip()
    customer_phone = str(echo.get("to") or echo.get("recipient_id") or "").strip()
    if not message_id or not phone_number_id or not customer_phone:
        raise ValueError("Echo identifiers are required.")
    message_type = str(echo.get("type") or "text")
    text = ""
    if message_type == "text":
        text = str((echo.get("text") or {}).get("body") or echo.get("body") or "")
    timestamp = None
    try:
        timestamp = datetime.fromtimestamp(int(echo.get("timestamp")), tz=timezone.get_current_timezone())
    except (TypeError, ValueError, OSError):
        pass
    return {
        "message_id": message_id,
        "phone_number_id": phone_number_id,
        "customer_phone": customer_phone,
        "content_type": message_type if message_type in {"text", "image", "audio", "document", "video"} else "unsupported",
        "text": text,
        "visibility": str(echo.get("visibility") or "public"),
        "timestamp": timestamp,
        "correlation_id": uuid.UUID(str(echo["correlation_id"])) if echo.get("correlation_id") else uuid.uuid4(),
    }
