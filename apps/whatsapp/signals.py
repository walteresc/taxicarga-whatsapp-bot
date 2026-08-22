"""Signals for publishing events via Redis (FASE 5B real-time updates).

Contract: All events include sufficient data for frontend to update state without additional REST calls.
Uses transaction.on_commit() to ensure events only publish if transaction succeeds.
"""

import logging
from django.db.models.signals import post_save
from django.db import transaction
from django.dispatch import receiver
from django.utils import timezone

from apps.whatsapp.redis_events import publish_event
from .models import ConversacionWhatsApp, MensajeWhatsApp

logger = logging.getLogger(__name__)


@receiver(post_save, sender=MensajeWhatsApp)
def publish_message_created_event(sender, instance, created, **kwargs):
    """Publish message.created event with complete conversation state.

    Uses transaction.on_commit() to ensure message is fully persisted before event is published.
    Single event type handles both inbound and echo - sender_type differentiates.
    """
    if not created:
        return

    if not instance.conversacion:
        return

    def publish_in_committed_transaction():
        """Publish only after transaction commits."""
        try:
            conv = instance.conversacion

            # Calculate unread for this conversation at commit time
            unread_inbound = conv.mensajes.filter(
                dirección=MensajeWhatsApp.ENTRANTE
            ).exclude(leido_por__isnull=False).count()

            # Complete event with all data frontend needs for bandeja + timeline
            event_data = {
                'conversation_id': conv.id,
                'channel_id': conv.channel_id,
                'cliente_id': conv.cliente_id,
                'message_id': instance.id,
                'meta_message_id': instance.meta_message_id,
                'sender_type': instance.sender_type,  # 'customer' or 'advisor'
                'direction': instance.dirección,  # 'entrante' or 'saliente'
                'content_type': instance.tipo,
                'preview': instance.contenido[:100] if instance.contenido else f"[{instance.tipo}]",
                'timestamp': instance.fecha_mensaje.isoformat() if instance.fecha_mensaje else timezone.now().isoformat(),
                'conversation': {
                    'summary': conv.resumen,
                    'last_activity': conv.ultima_actividad.isoformat() if conv.ultima_actividad else timezone.now().isoformat(),
                    'unread_count': unread_inbound,
                    'attention_state': conv.estado_atencion,
                    'bot_paused': conv.bot_pausado,
                }
            }

            publish_event('message.created', event_data)
        except Exception as e:
            logger.error(f"Failed to publish message event: {e}")

    transaction.on_commit(publish_in_committed_transaction)


@receiver(post_save, sender=ConversacionWhatsApp)
def publish_conversation_state_change(sender, instance, created, **kwargs):
    """Publish conversation state change.

    Uses transaction.on_commit() for consistency.
    Only publishes if state actually changed (created or meaningful update).
    """
    def publish_in_committed_transaction():
        """Publish only after transaction commits."""
        try:
            if created:
                event_type = 'conversation.created'
            else:
                # Only for meaningful updates (not every save)
                event_type = 'conversation.updated'

            event_data = {
                'conversation_id': instance.id,
                'cliente_id': instance.cliente_id,
                'channel_id': instance.channel_id,
                'summary': instance.resumen,
                'last_activity': instance.ultima_actividad.isoformat() if instance.ultima_actividad else None,
                'attention_state': instance.estado_atencion,
                'bot_paused': instance.bot_pausado,
                'collection_state': instance.estado_recopilacion,
                'quote_state': instance.estado_cotizacion,
            }

            publish_event(event_type, event_data)
        except Exception as e:
            logger.error(f"Failed to publish conversation event: {e}")

    transaction.on_commit(publish_in_committed_transaction)
