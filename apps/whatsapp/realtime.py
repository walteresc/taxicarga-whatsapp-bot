"""
Real-time event broadcasting for WhatsApp conversations.
Uses Django signals to emit server-sent events when messages are created.
"""
from django.dispatch import receiver
from django.db.models.signals import post_save
from apps.whatsapp.models import MensajeWhatsApp
import logging

logger = logging.getLogger(__name__)

# In-memory event subscribers (in production: use Redis/Channels)
_subscribers = {}


def subscribe_to_conversation(conversation_id, client_id):
    """Register a client to receive events for a conversation"""
    if conversation_id not in _subscribers:
        _subscribers[conversation_id] = set()
    _subscribers[conversation_id].add(client_id)
    logger.info(f"[RealTime] Client {client_id} subscribed to conv {conversation_id}")


def unsubscribe_from_conversation(conversation_id, client_id):
    """Unregister a client"""
    if conversation_id in _subscribers:
        _subscribers[conversation_id].discard(client_id)
        logger.info(f"[RealTime] Client {client_id} unsubscribed from conv {conversation_id}")


def broadcast_message_event(message):
    """
    Broadcast message.created event to all subscribers of the conversation.
    In production, this would publish to Redis/Channels.
    """
    conv_id = message.conversacion_id
    if conv_id not in _subscribers or not _subscribers[conv_id]:
        return

    event_data = {
        "event_type": "message.created",
        "conversation_id": conv_id,
        "message": {
            "id": message.id,
            "wamid": message.meta_message_id,
            "direction": message.direccion,
            "sender_type": message.sender_type,
            "source": message.source,
            "text": message.contenido[:200],
            "timestamp": message.fecha_mensaje.isoformat(),
        }
    }

    logger.info(f"[RealTime] Broadcasting message {message.id} to {len(_subscribers[conv_id])} clients")
    # In production: queue to Redis stream or Django Channels group
    # For now: just log the event


def broadcast_conversation_event(conversation, event_type="conversation.updated"):
    """
    Broadcast conversation state change (takeover, etc).
    """
    conv_id = conversation.id
    if conv_id not in _subscribers or not _subscribers[conv_id]:
        return

    event_data = {
        "event_type": event_type,
        "conversation_id": conv_id,
        "conversation": {
            "id": conversation.id,
            "resumen": conversation.resumen,
            "ultima_actividad": conversation.ultima_actividad.isoformat() if conversation.ultima_actividad else None,
            "bot_pausado": conversation.bot_pausado,
            "estado_atencion": conversation.estado_atencion,
        }
    }

    logger.info(f"[RealTime] Broadcasting {event_type} for conv {conv_id}")
    # In production: queue to Redis stream or Django Channels group
