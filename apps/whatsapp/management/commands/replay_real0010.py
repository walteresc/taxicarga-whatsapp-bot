"""
Republish REAL-0010 event to Redis for real-time delivery test.
"""
import sys
import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.whatsapp.models import MensajeWhatsApp, ConversacionWhatsApp
from apps.whatsapp.redis_events import get_event_bus


class Command(BaseCommand):
    help = "Republish REAL-0010 message to Redis for real-time delivery"

    def handle(self, *args, **options):
        # Find message with pk=145 (REAL-0010)
        try:
            msg = MensajeWhatsApp.objects.get(pk=145)
        except MensajeWhatsApp.DoesNotExist:
            self.stdout.write(self.style.ERROR("Message 145 not found"))
            sys.exit(1)

        conv = msg.conversacion

        self.stdout.write(f"[REPLAY] Found REAL-0010: msg_id={msg.id}, meta_message_id={msg.meta_message_id}")
        self.stdout.write(f"[REPLAY] Conversation: conv_id={conv.id}, cliente_id={conv.cliente_id}")

        # Get event bus
        bus = get_event_bus()
        if not bus.is_available():
            self.stdout.write(self.style.ERROR("Redis unavailable"))
            sys.exit(1)

        # Build event payload (same as original but with replay_of flag)
        event_data = {
            "type": "message.created",
            "channel_id": conv.channel_id,
            "conversation_id": conv.id,
            "message_id": msg.id,
            "meta_message_id": msg.meta_message_id,
            "from": conv.cliente.telefono,
            "content": msg.contenido,
            "direction": msg.direccion,
            "origen": msg.origen,
            "tipo": msg.tipo,
            "timestamp": msg.fecha_mensaje.isoformat(),
            "correlation_id": f"REPLAY-{msg.id}",
            "replay_of": "REAL-0010"  # Mark as replay
        }

        try:
            # Publish to Redis stream with new stream ID (posterior to current cursor)
            # Current cursor is 1787785056227-0, so new stream IDs will be auto-generated posterior
            stream_id = bus.publish("message.created", event_data)
            self.stdout.write(self.style.SUCCESS(f"[REPLAY] Event published to Redis with stream_id={stream_id}"))

            # Also publish conversation.updated event
            conv_event = {
                "type": "conversation.updated",
                "channel_id": conv.channel_id,
                "conversation_id": conv.id,
                "last_message_id": msg.id,
                "timestamp": timezone.now().isoformat(),
                "correlation_id": f"REPLAY-CONV-{msg.id}",
                "replay_of": "REAL-0010"
            }
            bus.publish("conversation.updated", conv_event)
            self.stdout.write(self.style.SUCCESS("[REPLAY] Conversation event published"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error publishing to Redis: {e}"))
            import traceback
            traceback.print_exc()
            sys.exit(1)
