from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp.services import send_whatsapp_message
from apps.clientes.phone_identity import phone_for_meta

from ..enums import AuthorType, OutboxStatus, OwnerState, Provider
from ..models import (
    ConversationControl,
    ExternalMessageMapping,
    IntegrationOutboxEvent,
)
from .human_takeover import channel_is_stage7_scoped


@dataclass(frozen=True)
class MetaSendResult:
    event_id: str
    status: str
    sent: bool
    external_id: str = ""
    reason: str = ""


def _provider_message_id(result):
    if not isinstance(result, dict):
        return ""
    messages = result.get("messages") or []
    return str(messages[0].get("id") or "") if messages else ""


def _authorize(event, conversation, control):
    message = event.logical_message
    if not message or message.visibility != "public":
        return False, "missing_public_message"
    if message.author_type == AuthorType.BOT:
        allowed = (
            control.owner_state == OwnerState.BOT_ACTIVE
            and conversation.estado_atencion == ConversacionWhatsApp.ATENCION_BOT
            and not conversation.bot_pausado
        )
        return allowed, "bot_not_owner"
    if message.author_type == AuthorType.AGENT:
        if not settings.CHATWOOT_AGENT_TO_WHATSAPP_ENABLED:
            return False, "agent_delivery_disabled"
        allowed = (
            control.owner_state == OwnerState.AGENT_ACTIVE
            and conversation.estado_atencion == ConversacionWhatsApp.ATENCION_ASESOR
            and conversation.bot_pausado
        )
        return allowed, "agent_not_owner"
    return False, "unsupported_author"


def _lock_delivery_state(event_id, conversation_id):
    """Lock Stage 7 delivery rows in the global conversation/control/outbox order."""
    conversation = (
        ConversacionWhatsApp.objects.select_for_update(of=("self",))
        .select_related("cliente", "channel")
        .get(pk=conversation_id)
    )
    control, _ = ConversationControl.objects.get_or_create(conversation=conversation)
    control = ConversationControl.objects.select_for_update().get(pk=control.pk)
    event = (
        IntegrationOutboxEvent.objects.select_for_update(of=("self",))
        .select_related("logical_message")
        .get(pk=event_id)
    )
    return conversation, control, event


def process_meta_outbox_event(event_id, *, sender=send_whatsapp_message, worker_id="meta-sender"):
    if not settings.META_OUTBOX_ENABLED:
        return MetaSendResult(str(event_id), "disabled", False, reason="meta_outbox_disabled")
    event_ref = IntegrationOutboxEvent.objects.select_related("conversation").get(pk=event_id)
    if not channel_is_stage7_scoped(event_ref.conversation.channel_id):
        return MetaSendResult(str(event_id), "blocked", False, reason="outside_stage7_scope")

    with transaction.atomic():
        conversation, control, event = _lock_delivery_state(
            event_id, event_ref.conversation_id
        )
        if event.status == OutboxStatus.SENT:
            return MetaSendResult(str(event.id), event.status, False, event.external_id, "already_sent")
        if event.status not in {OutboxStatus.PENDING, OutboxStatus.RETRY} or event.available_at > timezone.now():
            return MetaSendResult(str(event.id), event.status, False, reason="not_claimable")
        allowed, reason = _authorize(event, conversation, control)
        if not allowed:
            if reason in {"bot_not_owner", "agent_not_owner", "missing_public_message", "unsupported_author"}:
                event.status = OutboxStatus.CANCELLED
                event.error_code = reason
                event.error_summary = "Meta delivery suppressed by ownership gate."
                event.save(update_fields=["status", "error_code", "error_summary", "updated_at"])
            return MetaSendResult(str(event.id), event.status, False, reason=reason)
        event.status = OutboxStatus.SENDING
        event.attempts += 1
        event.locked_at = timezone.now()
        event.locked_by = worker_id
        event.save(update_fields=["status", "attempts", "locked_at", "locked_by", "updated_at"])
        message = event.logical_message
        recipient = phone_for_meta(conversation.cliente.telefono)
        channel = conversation.channel

    try:
        result = sender(
            recipient,
            message.text,
            channel=channel,
            author_type=message.author_type,
            conversation_id=conversation.id,
        )
    except Exception:
        result = {"sent": False, "reason": "ambiguous_exception", "status_code": None}
    external_id = _provider_message_id(result)
    if external_id:
        with transaction.atomic():
            conversation, _control, event = _lock_delivery_state(
                event_id, event_ref.conversation_id
            )
            event.status = OutboxStatus.SENT
            event.sent_at = timezone.now()
            event.external_id = external_id
            event.locked_at = None
            event.locked_by = ""
            event.error_code = ""
            event.error_summary = ""
            event.save()
            ExternalMessageMapping.objects.get_or_create(
                provider=Provider.META_WHATSAPP,
                account_scope=str(channel.phone_number_id),
                external_id=external_id,
                defaults={"logical_message": message},
            )
            MensajeWhatsApp.objects.get_or_create(
                meta_message_id=external_id,
                defaults={
                    "conversacion": conversation,
                    "direccion": MensajeWhatsApp.SALIENTE,
                    "origen": (
                        MensajeWhatsApp.ORIGEN_ASESOR
                        if message.author_type == AuthorType.AGENT
                        else MensajeWhatsApp.ORIGEN_BOT
                    ),
                    "contenido": message.text,
                    "estado": "enviado",
                },
            )
            commercial = event.event_type == "send_commercial_quote"
        if commercial:
            from apps.cotizador.delivery import mark_commercial_outbox_sent
            mark_commercial_outbox_sent(event_id, external_id)
        return MetaSendResult(str(event_id), OutboxStatus.SENT, True, external_id)

    status_code = result.get("status_code") if isinstance(result, dict) else None
    reason = str(result.get("reason") or "ambiguous_result") if isinstance(result, dict) else "ambiguous_result"
    transient = status_code in {408, 429} or (isinstance(status_code, int) and status_code >= 500) or status_code is None
    with transaction.atomic():
        event = IntegrationOutboxEvent.objects.select_for_update().get(pk=event_id)
        exhausted = event.attempts >= event.max_attempts
        event.status = OutboxStatus.RETRY if transient and not exhausted else OutboxStatus.DEAD_LETTER
        event.available_at = timezone.now() + timedelta(seconds=min(300, 5 * (2 ** max(event.attempts - 1, 0))))
        event.locked_at = None
        event.locked_by = ""
        event.error_code = "ambiguous_meta_result" if status_code is None else f"http_{status_code}"
        event.error_summary = reason[:255]
        event.save()
        commercial = event.event_type == "send_commercial_quote"
        error_code = event.error_code
        error_summary = event.error_summary
        retrying = event.status == OutboxStatus.RETRY
    if commercial:
        from apps.cotizador.delivery import mark_commercial_outbox_failed
        mark_commercial_outbox_failed(event_id, error_code, error_summary, retrying)
    return MetaSendResult(str(event_id), event.status, False, reason=event.error_code)
