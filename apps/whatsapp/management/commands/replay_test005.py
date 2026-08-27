"""
Development-only command: Replay TEST-005 message via Redis SSE.
Does NOT create new PostgreSQL entries or trigger bot.
"""
from django.core.management.base import BaseCommand
from apps.whatsapp.models import MensajeWhatsApp
from apps.whatsapp.redis_events import get_event_bus
import json


class Command(BaseCommand):
    help = "Replay MensajeWhatsApp ID 117 via Redis SSE (dev only)"

    def handle(self, *args, **options):
        # Get TEST-005 message
        msg = MensajeWhatsApp.objects.filter(id=117).first()
        if not msg:
            self.stdout.write(self.style.ERROR("Message ID 117 not found"))
            return

        # Build SSE event from existing message
        event_data = {
            "conversation_id": msg.conversacion_id,
            "channel_id": msg.conversacion.channel_id,
            "cliente_id": msg.conversacion.cliente_id,
            "message_id": msg.id,
            "meta_message_id": msg.meta_message_id,
            "sender_type": msg.sender_type,
            "direction": msg.direccion,
            "content_type": msg.tipo,
            "preview": msg.contenido,
            "timestamp": msg.fecha_mensaje.isoformat(),
            "conversation": {
                "summary": msg.conversacion.resumen,
                "last_activity": msg.conversacion.ultima_actividad.isoformat(),
                "unread_delta": 0,  # No change
                "attention_state": msg.conversacion.estado_atencion,
                "bot_paused": msg.conversacion.bot_pausado,
            },
        }

        # Publish to Redis (new event ID, same message)
        try:
            bus = get_event_bus()
            event = bus.publish("message.created", event_data)
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Replay published: event_id={event.id}, msg_id={msg.id}"
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Publish failed: {e}"))
