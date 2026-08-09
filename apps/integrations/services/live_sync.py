from django.conf import settings
from django.db import IntegrityError, transaction

from apps.whatsapp.domain import obtener_o_crear_conversacion
from apps.whatsapp.models import MensajeWhatsApp

from ..models import ConversationControl
from .chatwoot_projection import sync_chatwoot_conversation
from .human_takeover import channel_is_stage7_scoped


def canonical_incoming_message(*, lead, channel, event, conversation=None):
    """Persist one canonical TEST inbound by Meta provider id."""
    if not channel or not channel_is_stage7_scoped(channel.id):
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
    except IntegrityError:
        message = MensajeWhatsApp.objects.get(
            meta_message_id=str(event.get("message_id") or "")
        )
        created = False
    return message, created, conversation


def project_new_incoming(message, *, client=None):
    if not message or not settings.CHATWOOT_LIVE_SYNC_ENABLED:
        return None
    if not channel_is_stage7_scoped(message.conversacion.channel_id):
        return None
    return sync_chatwoot_conversation(
        message.conversacion_id,
        message_ids=[message.id],
        live=True,
        client=client,
    )
