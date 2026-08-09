from dataclasses import dataclass

from django.db import transaction

from apps.whatsapp.models import ConversacionWhatsApp

from ..enums import OutboxStatus, Provider
from ..models import ConversationMapping, IntegrationOutboxEvent
from ..providers.chatwoot.client import ChatwootClient
from .channel_policy import is_feature_enabled


COMMERCIAL_LABELS = {"por-cotizar", "cotizado"}


@dataclass(frozen=True)
class LabelProjectionResult:
    status: str
    labels: tuple[str, ...] = ()


def desired_commercial_labels(state):
    if state == ConversacionWhatsApp.COTIZACION_PENDIENTE:
        return {"por-cotizar"}
    if state == ConversacionWhatsApp.COTIZACION_PRECIO_ENVIADO:
        return {"cotizado"}
    return set()


def queue_commercial_label_projection(conversation_id):
    conversation = ConversacionWhatsApp.objects.select_related("channel").get(pk=conversation_id)
    if not is_feature_enabled(conversation.channel, "commercial_labels"):
        return None, False
    mapping = ConversationMapping.objects.select_related(
        "contact_inbox__inbox__account"
    ).filter(conversation=conversation, active=True).first()
    if not mapping:
        return None, False
    evidence = _evidence_key(conversation)
    return IntegrationOutboxEvent.objects.get_or_create(
        destination=Provider.CHATWOOT,
        destination_scope=str(mapping.contact_inbox.inbox.account.account_id),
        idempotency_key=f"commercial-label:{conversation.id}:{conversation.estado_cotizacion}:{evidence}",
        defaults={
            "event_type": "sync_commercial_labels",
            "conversation": conversation,
            "safe_payload": {
                "conversation_mapping_id": mapping.id,
                "commercial_state": conversation.estado_cotizacion,
            },
        },
    )


def process_commercial_label_event(event_id, *, client=None, force=False):
    with transaction.atomic():
        event = IntegrationOutboxEvent.objects.select_for_update().select_related(
            "conversation__channel"
        ).get(pk=event_id)
        if not is_feature_enabled(event.conversation.channel, "commercial_labels"):
            return LabelProjectionResult("disabled")
        if event.status == OutboxStatus.SENT and not force:
            return LabelProjectionResult("already_sent")
        mapping = ConversationMapping.objects.select_related(
            "conversation__channel", "contact_inbox__inbox__account"
        ).get(
            pk=event.safe_payload["conversation_mapping_id"], active=True
        )
        if (
            mapping.conversation_id != event.conversation_id
            or mapping.contact_inbox.inbox.channel_id != event.conversation.channel_id
        ):
            event.status = OutboxStatus.DEAD_LETTER
            event.error_code = "channel_scope_mismatch"
            event.error_summary = "Commercial label mapping channel is invalid."
            event.save(update_fields=["status", "error_code", "error_summary", "updated_at"])
            return LabelProjectionResult("dead_letter")
        event.status = OutboxStatus.SENDING
        event.attempts += 1
        event.save(update_fields=["status", "attempts", "updated_at"])
        external_id = mapping.external_conversation_id
        desired = desired_commercial_labels(mapping.conversation.estado_cotizacion)
    api = client or ChatwootClient()
    try:
        for title in COMMERCIAL_LABELS:
            api.ensure_label(title)
        payload = api.get_conversation(external_id)
        current = set(payload.get("labels") or [])
        final = (current - COMMERCIAL_LABELS) | desired
        api.set_conversation_labels(external_id, final)
    except Exception as exc:
        IntegrationOutboxEvent.objects.filter(pk=event_id).update(
            status=OutboxStatus.RETRY, error_code="chatwoot_label_error",
            error_summary=str(exc)[:255], locked_at=None, locked_by="",
        )
        return LabelProjectionResult("retry")
    IntegrationOutboxEvent.objects.filter(pk=event_id).update(
        status=OutboxStatus.SENT, error_code="", error_summary="",
    )
    return LabelProjectionResult("sent", tuple(sorted(final)))


def _evidence_key(conversation):
    if conversation.estado_cotizacion == ConversacionWhatsApp.COTIZACION_PENDIENTE:
        value = conversation.solicitudes_cotizacion.filter(
            estado__in=["pendiente", "en_proceso"]
        ).order_by("-id").values_list("id", flat=True).first()
        return value or "none"
    value = conversation.lead.cotizaciones_comerciales.filter(
        estado__in=["enviada", "entregada", "en_negociacion", "aceptada"]
    ).order_by("-id").values_list("id", flat=True).first() if conversation.lead_id else None
    return value or "none"
