"""Signals for publishing events via Redis (FASE 5B real-time updates).

Contract: All events include sufficient data for frontend to update state without additional REST calls.
Uses transaction.on_commit() to ensure events only publish if transaction succeeds.

REAL VALUE DETECTION:
- pre_save: captures old values from DB for SIGNIFICANT_FIELDS
- post_save: compares old vs new, only emits if values actually changed
- Handles: new instances, rollbacks, update_fields optimization, FK fields, datetime
"""

import logging
from django.db.models.signals import pre_save, post_save
from django.db import transaction
from django.dispatch import receiver
from django.utils import timezone

from apps.whatsapp.redis_events import publish_event
from .models import ConversacionWhatsApp, MensajeWhatsApp

logger = logging.getLogger(__name__)

# SIGNIFICANT_FIELDS for ConversacionWhatsApp (defined at module level for reuse)
CONVERSATION_SIGNIFICANT_FIELDS = {
    'resumen',
    'ultima_actividad',
    'estado_atencion',
    'bot_pausado',
    'responsable_id',
    'estado_recopilacion',
    'estado_cotizacion',
    'cerrada_en',
}


@receiver(pre_save, sender=ConversacionWhatsApp)
def capture_old_values(sender, instance, **kwargs):
    """Capture old values from DB before save (for change detection).

    Stores snapshot of previous values in instance._old_values dict.
    Used by post_save handler to determine if values actually changed.
    """
    using = kwargs.get('using', 'default')

    # Check if this is a new instance (no PK yet)
    if instance.pk is None:
        instance._old_values = {}
        instance._is_new = True
        return

    instance._is_new = False

    try:
        # Query DB for current values (before this save overwrites them)
        db_instance = ConversacionWhatsApp.objects.using(using).get(pk=instance.pk)

        # Capture only SIGNIFICANT_FIELDS
        instance._old_values = {
            field: getattr(db_instance, field, None)
            for field in CONVERSATION_SIGNIFICANT_FIELDS
        }

        logger.debug(f"[pre_save] Conv {instance.pk}: captured old values {list(instance._old_values.keys())}")
    except ConversacionWhatsApp.DoesNotExist:
        # Race condition: instance existed, then got deleted
        # Treat as if new
        instance._old_values = {}
        logger.warning(f"[pre_save] Conv {instance.pk}: not found in DB (race?), treating as new")
    except Exception as e:
        # Fallback: log but don't crash
        logger.error(f"[pre_save] Conv {instance.pk}: failed to capture old values: {e}")
        instance._old_values = {}


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

            # Calculate unread CANONICAL: only new messages since last read (at time of event)
            # This MUST match ConversationReadState calculation for consistency
            # Don't count all unread inbound - that's stale. Count ONLY new messages after event.
            # For simplicity: message just arrived = +1 unread for first viewer
            unread_delta = 1 if instance.direccion == MensajeWhatsApp.ENTRANTE else 0

            # Complete event with all data frontend needs for bandeja + timeline
            event_data = {
                'conversation_id': conv.id,
                'channel_id': conv.channel_id,
                'cliente_id': conv.cliente_id,
                'message_id': instance.id,
                'meta_message_id': instance.meta_message_id,
                'sender_type': instance.sender_type,  # 'customer' or 'advisor'
                'direction': instance.direccion,  # 'entrante' or 'saliente'
                'content_type': instance.tipo,
                'preview': instance.contenido[:100] if instance.contenido else f"[{instance.tipo}]",
                'timestamp': instance.fecha_mensaje.isoformat() if instance.fecha_mensaje else timezone.now().isoformat(),
                'conversation': {
                    'summary': conv.resumen,
                    'last_activity': conv.ultima_actividad.isoformat() if conv.ultima_actividad else timezone.now().isoformat(),
                    'unread_delta': unread_delta,
                    'attention_state': conv.estado_atencion,
                    'bot_paused': conv.bot_pausado,
                }
            }

            logger.warning(f"[CP-12] SIGNAL_EXECUTED: message.created signal fired for msg_id={instance.id}")
            event = publish_event('message.created', event_data)
            logger.warning(f"[CP-13] REDIS_EVENT_PUBLISHED: event_id={event.id if event else 'failed'}, type=message.created")
        except Exception as e:
            logger.error(f"Failed to publish message event: {e}")

    logger.warning(f"[CP-11.5] ON_COMMIT_REGISTERED: registering publish for msg_id={instance.id}")
    transaction.on_commit(publish_in_committed_transaction)


@receiver(post_save, sender=ConversacionWhatsApp)
def publish_conversation_state_change(sender, instance, created, update_fields=None, **kwargs):
    """Publish conversation state change ONLY if values actually changed (not just update_fields presence).

    Uses real value comparison:
    - created=True: always emit conversation.created
    - created=False: compare old vs new values, emit conversation.updated only if changed
    - Uses transaction.on_commit() for consistency

    Pre-requisite: pre_save handler must run first to capture old values in instance._old_values
    """

    # Determine if we should publish and what to publish
    should_publish = False
    event_type = None
    changed_fields = []

    if created:
        should_publish = True
        event_type = 'conversation.created'
    else:
        # Update case: compare old values with new values
        old_values = getattr(instance, '_old_values', {})

        # Determine which fields to check
        if update_fields is not None:
            # update_fields specified: only check significant fields in update_fields
            fields_to_check = CONVERSATION_SIGNIFICANT_FIELDS & set(update_fields)
        else:
            # update_fields=None: check all significant fields (Django didn't restrict)
            fields_to_check = CONVERSATION_SIGNIFICANT_FIELDS

        # Compare values
        for field_name in fields_to_check:
            old_value = old_values.get(field_name)
            new_value = getattr(instance, field_name, None)

            # Handle datetime comparison (normalize to string for comparison)
            if old_value != new_value:
                changed_fields.append(field_name)
                logger.debug(f"[post_save] Conv {instance.id}: {field_name} changed from {old_value!r} to {new_value!r}")

        # Publish only if there are real changes
        if changed_fields:
            should_publish = True
            event_type = 'conversation.updated'
        else:
            logger.debug(f"[post_save] Conv {instance.id}: no significant fields changed despite save() call")

    if not should_publish:
        return

    # Build immutable payload (copy values to avoid post-commit mutations)
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

    if event_type == 'conversation.updated' and changed_fields:
        event_data['changed_fields'] = changed_fields

    def publish_in_committed_transaction():
        """Publish only after transaction commits."""
        try:
            logger.info(f"[post_save] Publishing {event_type} for conversation {instance.id} (changed: {changed_fields})")
            publish_event(event_type, event_data)
        except Exception as e:
            logger.error(f"Failed to publish conversation event: {e}")

    transaction.on_commit(publish_in_committed_transaction)
