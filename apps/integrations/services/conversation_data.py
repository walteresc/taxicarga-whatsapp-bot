import hashlib
import json

from django.db import transaction

from apps.leads.cargo import effective_load_detail
from apps.leads.route import access_summary, route_summary
from apps.whatsapp.models import ConversacionWhatsApp

from ..enums import OutboxStatus, Provider
from ..models import ConversationMapping, IntegrationOutboxEvent
from ..providers.chatwoot.client import ChatwootClient
from .channel_policy import is_feature_enabled


ATTRIBUTE_DEFINITIONS = {
    "taxicarga_quote_status": "Estado cotizacion",
    "taxicarga_price": "Precio",
    "taxicarga_service": "Servicio",
    "taxicarga_route": "Ruta",
    "taxicarga_load": "Detalle de carga",
    "taxicarga_access": "Accesos",
    "taxicarga_operators": "Operarios",
    "taxicarga_additional": "Servicios adicionales",
    "taxicarga_date": "Fecha",
    "taxicarga_time": "Hora",
    "taxicarga_customer": "Nombre",
    "taxicarga_booking": "Reserva",
}


def conversation_snapshot(conversation):
    lead = conversation.lead
    if lead is None:
        return {}
    packing = lead.modalidad_servicio or "sin embalaje"
    extras = [packing]
    if lead.requiere_desarmado:
        extras.append("desarmado")
    if lead.requiere_armado:
        extras.append("armado")
    if lead.incluye_personal_carga is False:
        operators = "Sin operarios"
    elif lead.cantidad_operarios is not None:
        operators = f"{lead.cantidad_operarios} operarios"
    elif lead.incluye_personal_carga:
        operators = "Con operarios"
    else:
        operators = "Por definir"
    service = getattr(lead, "servicio_generado", None)
    return {
        "taxicarga_quote_status": conversation.estado_cotizacion,
        "taxicarga_price": str(lead.precio_cotizado or ""),
        "taxicarga_service": lead.tipo_servicio or "",
        "taxicarga_route": route_summary(lead),
        "taxicarga_load": effective_load_detail(lead),
        "taxicarga_access": access_summary(lead),
        "taxicarga_operators": operators,
        "taxicarga_additional": " · ".join(extras),
        "taxicarga_date": lead.fecha_servicio.isoformat() if lead.fecha_servicio else "",
        "taxicarga_time": lead.horario_servicio or "",
        "taxicarga_customer": lead.cliente.nombre or "",
        "taxicarga_booking": service.codigo if service else "Pendiente",
    }


def queue_conversation_data_projection(conversation_id):
    conversation = ConversacionWhatsApp.objects.select_related("channel", "lead").get(pk=conversation_id)
    if not is_feature_enabled(conversation.channel, "live_sync"):
        return None, False
    mapping = ConversationMapping.objects.select_related("contact_inbox__inbox__account").filter(
        conversation=conversation, active=True
    ).first()
    if not mapping:
        return None, False
    snapshot = conversation_snapshot(conversation)
    if not snapshot:
        return None, False
    evidence = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()[:16]
    return IntegrationOutboxEvent.objects.get_or_create(
        destination=Provider.CHATWOOT,
        destination_scope=str(mapping.contact_inbox.inbox.account.account_id),
        idempotency_key=f"conversation-data:{conversation.id}:{evidence}",
        defaults={
            "event_type": "sync_conversation_data",
            "conversation": conversation,
            "safe_payload": {"conversation_mapping_id": mapping.id, "attributes": snapshot},
        },
    )


def process_conversation_data_event(event_id, *, client=None):
    with transaction.atomic():
        event = IntegrationOutboxEvent.objects.select_for_update().get(pk=event_id)
        if event.status == OutboxStatus.SENT:
            return "already_sent"
        mapping = ConversationMapping.objects.select_related("contact_inbox__inbox").get(
            pk=event.safe_payload["conversation_mapping_id"], active=True
        )
        if mapping.conversation_id != event.conversation_id or mapping.contact_inbox.inbox.channel_id != event.conversation.channel_id:
            event.status = OutboxStatus.DEAD_LETTER
            event.error_code = "channel_scope_mismatch"
            event.save(update_fields=["status", "error_code", "updated_at"])
            return "dead_letter"
        event.status = OutboxStatus.SENDING
        event.attempts += 1
        event.save(update_fields=["status", "attempts", "updated_at"])
    api = client or ChatwootClient()
    try:
        remote = api.get_conversation(mapping.external_conversation_id)
        attributes = dict(remote.get("custom_attributes") or {}) if isinstance(remote, dict) else {}
        attributes.update(event.safe_payload["attributes"])
        api.update_conversation_custom_attributes(
            mapping.external_conversation_id, attributes
        )
    except Exception as exc:
        IntegrationOutboxEvent.objects.filter(pk=event_id).update(
            status=OutboxStatus.RETRY, error_code="chatwoot_attribute_error",
            error_summary=str(exc)[:255], locked_at=None, locked_by="",
        )
        return "retry"
    IntegrationOutboxEvent.objects.filter(pk=event_id).update(
        status=OutboxStatus.SENT, error_code="", error_summary=""
    )
    return "sent"
