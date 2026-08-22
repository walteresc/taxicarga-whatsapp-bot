"""Signals for publishing events to event bus (FASE 5B real-time updates)."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.whatsapp.events_service import publish_event
from .models import ConversacionWhatsApp, MensajeWhatsApp


@receiver(post_save, sender=MensajeWhatsApp)
def publish_message_created_event(sender, instance, created, **kwargs):
    """Publish event when message is created."""
    if not created:
        return

    if not instance.conversacion:
        return

    event_data = {
        'conversation_id': instance.conversacion_id,
        'message_id': instance.id,
        'sender_type': instance.sender_type,
        'direction': instance.dirección,
        'timestamp': instance.fecha_mensaje.isoformat() if instance.fecha_mensaje else None,
    }

    publish_event('message_created', event_data)

    # Also publish conversation_update with new preview
    publish_event('conversation_update', {
        'conversation_id': instance.conversacion_id,
        'preview': instance.contenido[:100] if instance.contenido else f"[{instance.tipo}]",
        'last_activity': instance.fecha_mensaje.isoformat() if instance.fecha_mensaje else None,
    })


@receiver(post_save, sender=ConversacionWhatsApp)
def publish_conversation_state_change(sender, instance, created, **kwargs):
    """Publish event when conversation state changes."""
    if created:
        event_type = 'conversation_created'
    else:
        event_type = 'conversation_updated'

    event_data = {
        'conversation_id': instance.id,
        'cliente_id': instance.cliente_id,
        'channel_id': instance.channel_id,
        'estado_atencion': instance.estado_atencion,
        'estado_recopilacion': instance.estado_recopilacion,
        'estado_cotizacion': instance.estado_cotizacion,
    }

    publish_event(event_type, event_data)
