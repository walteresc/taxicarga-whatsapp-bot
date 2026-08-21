"""Test message persistence: verify ultima_actividad and resumen are saved atomically."""
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import connection
from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel, MensajeWhatsApp
from apps.whatsapp.services import process_whatsapp_message


class Command(BaseCommand):
    help = 'Test message persistence fix'

    def handle(self, *args, **options):
        self.stdout.write("[TEST] Message Persistence Verification\n")

        # Setup
        cliente, _ = Cliente.objects.get_or_create(
            telefono="+51999999999",
            defaults={"nombre": "Test Walter"}
        )
        channel, _ = WhatsAppChannel.objects.get_or_create(
            phone_number_id="123456789",
            defaults={"asesor_id": 1, "activo": True}
        )

        # Clear previous test conversation
        ConversacionWhatsApp.objects.filter(cliente=cliente).delete()

        # Create initial conversation
        conversation = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=channel,
        )
        self.stdout.write(f"Initial: id={conversation.id}, ultima_actividad={conversation.ultima_actividad}, resumen={conversation.resumen}")

        # Test 1: Process first message at 10:31
        ts_1031 = timezone.make_aware(datetime(2026, 8, 21, 10, 31, 0))
        event_1 = {
            "message_id": "wamid_001",
            "timestamp": str(int(ts_1031.timestamp())),
            "text": "mensaje test a las 10:31",
            "created_at": None,
        }

        result1 = process_whatsapp_message(
            client=cliente,
            channel=channel,
            event=event_1,
            direction=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            conversation=conversation,
        )
        conversation = result1["conversation"]
        conversation.refresh_from_db()

        self.stdout.write(f"\n[After Message 1 @ 10:31]")
        self.stdout.write(f"  DB: ultima_actividad={conversation.ultima_actividad}, resumen={conversation.resumen[:50]}")
        assert conversation.ultima_actividad == ts_1031, f"Expected {ts_1031}, got {conversation.ultima_actividad}"
        assert "10:31" in conversation.resumen, f"Expected '10:31' in resumen, got {conversation.resumen}"

        # Test 2: Process second message at 12:32 (later)
        ts_1232 = timezone.make_aware(datetime(2026, 8, 21, 12, 32, 0))
        event_2 = {
            "message_id": "wamid_002",
            "timestamp": str(int(ts_1232.timestamp())),
            "text": "probando7",
            "created_at": None,
        }

        result2 = process_whatsapp_message(
            client=cliente,
            channel=channel,
            event=event_2,
            direction=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            conversation=conversation,
        )
        conversation = result2["conversation"]
        conversation.refresh_from_db()

        self.stdout.write(f"\n[After Message 2 @ 12:32]")
        self.stdout.write(f"  DB: ultima_actividad={conversation.ultima_actividad}, resumen={conversation.resumen}")
        assert conversation.ultima_actividad == ts_1232, f"Expected {ts_1232}, got {conversation.ultima_actividad}"
        assert conversation.resumen == "probando7", f"Expected 'probando7', got {conversation.resumen}"

        self.stdout.write("\n[OK] ALL TESTS PASSED - ultima_actividad and resumen persist correctly\n")
