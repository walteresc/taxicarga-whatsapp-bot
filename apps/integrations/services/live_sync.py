from django.conf import settings
from django.db import IntegrityError, transaction

from apps.whatsapp.domain import obtener_o_crear_conversacion
from apps.whatsapp.models import MensajeWhatsApp

from ..enums import Provider
from ..models import ConversationControl, IntegrationOutboxEvent
from .channel_policy import integration_enabled, is_feature_enabled


def canonical_incoming_message(*, lead, channel, event, conversation=None):
    """Persist one canonical TEST inbound by Meta provider id."""
    if not channel or not integration_enabled(channel):
        return None, False, None
    conversation = conversation or obtener_o_crear_conversacion(lead)
    ConversationControl.objects.get_or_create(conversation=conversation)
    defaults = {
        "conversacion": conversation,
        "direccion": MensajeWhatsApp.ENTRANTE,
        "origen": MensajeWhatsApp.ORIGEN_CLIENTE,
        "tipo": "texto",
        "contenido": str(event.get("text") or ""),
        "estado": "recibido",
    }
    try:
        with transaction.atomic():
            message, created = MensajeWhatsApp.objects.get_or_create(
                meta_message_id=str(event.get("message_id") or ""), defaults=defaults
            )
            if is_feature_enabled(conversation.channel, "live_sync"):
                IntegrationOutboxEvent.objects.get_or_create(
                    destination=Provider.CHATWOOT,
                    destination_scope=str(conversation.channel_id),
                    idempotency_key=f"chatwoot-inbound:{message.id}",
                    defaults={
                        "event_type": "sync_inbound_message",
                        "conversation": conversation,
                        "safe_payload": {"message_ids": [message.id]},
                    },
                )
    except IntegrityError:
        message = MensajeWhatsApp.objects.get(
            meta_message_id=str(event.get("message_id") or "")
        )
        created = False
    return message, created, conversation


def project_new_incoming(message, *, client=None):
    """Compatibility helper. Queue only; never perform Chatwoot HTTP inline."""
    if not message:
        return None
    if not is_feature_enabled(message.conversacion.channel, "live_sync"):
        return None
    return IntegrationOutboxEvent.objects.get_or_create(
        destination=Provider.CHATWOOT,
        destination_scope=str(message.conversacion.channel_id),
        idempotency_key=f"chatwoot-inbound:{message.id}",
        defaults={
            "event_type": "sync_inbound_message",
            "conversation": message.conversacion,
            "safe_payload": {"message_ids": [message.id]},
        },
    )


def queue_outgoing_message_projection(message):
    """Queue one durable Chatwoot projection after Meta accepts an outgoing message."""
    if not message or message.direccion != MensajeWhatsApp.SALIENTE:
        return None, False
    if not is_feature_enabled(message.conversacion.channel, "live_sync"):
        return None, False
    return IntegrationOutboxEvent.objects.get_or_create(
        destination=Provider.CHATWOOT,
        destination_scope=str(message.conversacion.channel_id),
        idempotency_key=f"chatwoot-outbound:{message.id}",
        defaults={
            "event_type": "sync_outbound_message",
            "conversation": message.conversacion,
            "safe_payload": {"message_ids": [message.id]},
        },
    )
