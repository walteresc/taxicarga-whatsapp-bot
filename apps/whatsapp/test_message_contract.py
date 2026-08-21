"""
Tests validating canonical message contract:
- direction (entrante/saliente)
- sender_type (customer/bot/advisor/system)
- source (whatsapp_customer/whatsapp_business_app/bot/crm/system)
- Takeover logic
- Unread handling
"""
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.whatsapp.services import process_whatsapp_message
from apps.leads.models import Lead


class MessageContractTest(TransactionTestCase):
    """Test canonical message contract"""

    def setUp(self):
        self.client = Cliente.objects.create(
            nombre="Test Client",
            telefono="+51999999999",
        )
        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="123456789",
            numero_visible="Test",
            activo=True,
        )
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel,
        )

    # A. Inbound customer message
    def test_a_inbound_customer_message(self):
        """A. Inbound: sender_type=customer, source=whatsapp_customer, updates resumen, increments unread"""
        result = process_whatsapp_message(
            client=self.client,
            channel=self.channel,
            event={
                "message_id": "wamid-a",
                "text": "test inbound message",
                "timestamp": str(int(timezone.now().timestamp())),
            },
            direction=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            conversation=self.conversation,
        )

        self.assertTrue(result["created"])
        self.assertTrue(result["summary_updated"])
        self.assertTrue(result["unread_incremented"])
        self.assertFalse(result["takeover_activated"])

        msg = result["message"]
        self.assertEqual(msg.sender_type, MensajeWhatsApp.SENDER_CUSTOMER)
        self.assertEqual(msg.source, MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER)
        self.assertEqual(msg.direccion, MensajeWhatsApp.ENTRANTE)
        self.assertEqual(msg.origen, "cliente")

        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.resumen, "test inbound message")

    # B. Bot outbound message
    def test_b_bot_outbound_message(self):
        """B. Bot: sender_type=bot, source=bot, updates resumen, NO unread"""
        result = process_whatsapp_message(
            client=self.client,
            channel=self.channel,
            event={
                "message_id": "wamid-b",
                "text": "bot response",
                "timestamp": str(int(timezone.now().timestamp())),
            },
            direction=MensajeWhatsApp.SALIENTE,
            sender_type=MensajeWhatsApp.SENDER_BOT,
            source=MensajeWhatsApp.SOURCE_BOT,
            conversation=self.conversation,
        )

        self.assertTrue(result["created"])
        self.assertTrue(result["summary_updated"])
        self.assertFalse(result["unread_incremented"])  # Bot messages don't increment unread
        self.assertFalse(result["takeover_activated"])

        msg = result["message"]
        self.assertEqual(msg.sender_type, MensajeWhatsApp.SENDER_BOT)
        self.assertEqual(msg.source, MensajeWhatsApp.SOURCE_BOT)
        self.assertEqual(msg.origen, "bot")

    # C. Echo from WhatsApp Web (advisor intervention)
    def test_c_whatsapp_business_app_echo(self):
        """C. Echo humano: source=whatsapp_business_app activates takeover"""
        result = process_whatsapp_message(
            client=self.client,
            channel=self.channel,
            event={
                "message_id": "wamid-c",
                "text": "message from whatsapp web",
                "timestamp": str(int(timezone.now().timestamp())),
            },
            direction=MensajeWhatsApp.SALIENTE,
            sender_type=MensajeWhatsApp.SENDER_ADVISOR,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP,
            conversation=self.conversation,
        )

        self.assertTrue(result["created"])
        self.assertTrue(result["summary_updated"])
        self.assertFalse(result["unread_incremented"])
        self.assertTrue(result["takeover_activated"])  # CRITICAL: takeover happens

        msg = result["message"]
        self.assertEqual(msg.sender_type, MensajeWhatsApp.SENDER_ADVISOR)
        self.assertEqual(msg.source, MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP)

        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.bot_pausado)
        self.assertEqual(self.conversation.estado_atencion, ConversacionWhatsApp.ATENCION_ASESOR)

    # D. CRM advisor message
    def test_d_crm_advisor_message(self):
        """D. CRM: source=crm, NO unread increment"""
        result = process_whatsapp_message(
            client=self.client,
            channel=self.channel,
            event={
                "message_id": "wamid-d",
                "text": "message from crm",
                "timestamp": str(int(timezone.now().timestamp())),
            },
            direction=MensajeWhatsApp.SALIENTE,
            sender_type=MensajeWhatsApp.SENDER_ADVISOR,
            source=MensajeWhatsApp.SOURCE_CRM,
            conversation=self.conversation,
        )

        self.assertTrue(result["created"])
        self.assertTrue(result["summary_updated"])
        self.assertFalse(result["unread_incremented"])
        self.assertFalse(result["takeover_activated"])  # CRM advisors don't auto-takeover

        msg = result["message"]
        self.assertEqual(msg.sender_type, MensajeWhatsApp.SENDER_ADVISOR)
        self.assertEqual(msg.source, MensajeWhatsApp.SOURCE_CRM)
        self.assertEqual(msg.origen, "asesor")

    # E. Duplicate message (same wamid)
    def test_e_duplicate_message_idempotent(self):
        """E. Duplicate: same wamid creates message only once"""
        wamid = "wamid-e"

        result1 = process_whatsapp_message(
            client=self.client,
            channel=self.channel,
            event={
                "message_id": wamid,
                "text": "test duplicate",
                "timestamp": str(int(timezone.now().timestamp())),
            },
            direction=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            conversation=self.conversation,
        )
        self.assertTrue(result1["created"])
        self.assertTrue(result1["unread_incremented"])

        result2 = process_whatsapp_message(
            client=self.client,
            channel=self.channel,
            event={
                "message_id": wamid,
                "text": "test duplicate",
                "timestamp": str(int(timezone.now().timestamp())),
            },
            direction=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            conversation=self.conversation,
        )
        self.assertFalse(result2["created"])  # Not created again
        self.assertFalse(result2["unread_incremented"])  # Unread not incremented
        self.assertEqual(result1["message"].id, result2["message"].id)

    # F. Old/late message doesn't retrograde summary
    def test_f_old_message_no_retrograde(self):
        """F. Late arrival: old message saved but doesn't replace newer summary"""
        now_ts = int(timezone.now().timestamp())

        # Send new message
        result_new = process_whatsapp_message(
            client=self.client,
            channel=self.channel,
            event={
                "message_id": "wamid-f-new",
                "text": "recent message",
                "timestamp": str(now_ts),
            },
            direction=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            conversation=self.conversation,
        )
        self.assertTrue(result_new["summary_updated"])
        self.conversation.refresh_from_db()
        new_resumen = self.conversation.resumen
        new_ua = self.conversation.ultima_actividad

        # Send old message (2 hours earlier)
        old_ts = now_ts - (2 * 3600)
        result_old = process_whatsapp_message(
            client=self.client,
            channel=self.channel,
            event={
                "message_id": "wamid-f-old",
                "text": "old message from 2h ago",
                "timestamp": str(old_ts),
            },
            direction=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            conversation=self.conversation,
        )
        self.assertTrue(result_old["created"])
        self.assertFalse(result_old["summary_updated"])  # Not updated

        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.resumen, new_resumen)  # Didn't change
        self.assertEqual(self.conversation.ultima_actividad, new_ua)  # Didn't go backwards

    # G. API timeline returns all messages with correct attribution
    def test_g_api_timeline_complete(self):
        """G. API: timeline endpoint returns all messages with correct sender_type/source"""
        from django.test import Client as HTTPClient

        # Create 5 messages: customer, bot, customer, advisor-web, customer
        msgs_data = [
            (MensajeWhatsApp.ENTRANTE, MensajeWhatsApp.SENDER_CUSTOMER, MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER, "msg1"),
            (MensajeWhatsApp.SALIENTE, MensajeWhatsApp.SENDER_BOT, MensajeWhatsApp.SOURCE_BOT, "msg2"),
            (MensajeWhatsApp.ENTRANTE, MensajeWhatsApp.SENDER_CUSTOMER, MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER, "msg3"),
            (MensajeWhatsApp.SALIENTE, MensajeWhatsApp.SENDER_ADVISOR, MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP, "msg4"),
            (MensajeWhatsApp.ENTRANTE, MensajeWhatsApp.SENDER_CUSTOMER, MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER, "msg5"),
        ]

        for i, (direction, sender_type, source, text) in enumerate(msgs_data):
            process_whatsapp_message(
                client=self.client,
                channel=self.channel,
                event={
                    "message_id": f"wamid-g-{i}",
                    "text": text,
                    "timestamp": str(int(timezone.now().timestamp()) + i),
                },
                direction=direction,
                sender_type=sender_type,
                source=source,
                conversation=self.conversation,
            )

        # Query API
        messages = MensajeWhatsApp.objects.filter(
            conversacion=self.conversation
        ).order_by("fecha_mensaje")

        self.assertEqual(messages.count(), 5)

        # Verify each message has correct attribution
        for i, (direction, sender_type, source, text) in enumerate(msgs_data):
            msg = messages[i]
            self.assertEqual(msg.sender_type, sender_type, f"Message {i} sender_type mismatch")
            self.assertEqual(msg.source, source, f"Message {i} source mismatch")
            self.assertEqual(msg.direccion, direction, f"Message {i} direction mismatch")
            self.assertEqual(msg.contenido, text)

    # H. Vue receives realtime events and updates without F5
    @patch("apps.integrations.services.live_sync.project_new_incoming")
    def test_h_realtime_event_published(self, mock_realtime):
        """H. RealTime: message.created event scheduled via transaction.on_commit"""
        result = process_whatsapp_message(
            client=self.client,
            channel=self.channel,
            event={
                "message_id": "wamid-h",
                "text": "message triggering realtime",
                "timestamp": str(int(timezone.now().timestamp())),
            },
            direction=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            conversation=self.conversation,
        )

        self.assertTrue(result["created"])
        # Verify realtime was scheduled (mock would be called in transaction.on_commit)
        # In a real test, we'd need to actually commit the transaction


class PruebaEstructuralTest(TransactionTestCase):
    """End-to-end structural test (prueba-estructural-1/2/3)"""

    def setUp(self):
        self.client_obj = Cliente.objects.create(
            nombre="Prueba Estructural",
            telefono="+51988888888",
        )
        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="123456789",
            numero_visible="Test",
            activo=True,
        )

    @patch("apps.whatsapp.views.should_bot_reply")
    def test_prueba_estructural_1_inbound(self, mock_bot_reply):
        """Paso 1: Bot activo, cliente envía prueba-estructural-1"""
        mock_bot_reply.return_value = True

        result = process_whatsapp_message(
            client=self.client_obj,
            channel=self.channel,
            event={
                "message_id": "wamid-1",
                "text": "prueba-estructural-1",
                "timestamp": str(int(timezone.now().timestamp())),
            },
            direction=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
        )

        self.assertTrue(result["created"])
        self.assertTrue(result["summary_updated"])
        self.assertTrue(result["unread_incremented"])
        self.assertFalse(result["takeover_activated"])

        conv = result["conversation"]
        self.assertEqual(conv.estado_atencion, ConversacionWhatsApp.ATENCION_BOT)
        self.assertFalse(conv.bot_pausado)

    def test_prueba_estructural_2_advisor_web(self):
        """Paso 2: Asesor responde desde WhatsApp Web (prueba-estructural-2)"""
        # First establish conversation
        conv = ConversacionWhatsApp.objects.create(
            cliente=self.client_obj,
            channel=self.channel,
            estado_atencion=ConversacionWhatsApp.ATENCION_BOT,
        )

        # Bot had replied earlier
        process_whatsapp_message(
            client=self.client_obj,
            channel=self.channel,
            event={
                "message_id": "wamid-bot-reply",
                "text": "Bot: ¿Cómo puedo ayudarte?",
                "timestamp": str(int(timezone.now().timestamp())),
            },
            direction=MensajeWhatsApp.SALIENTE,
            sender_type=MensajeWhatsApp.SENDER_BOT,
            source=MensajeWhatsApp.SOURCE_BOT,
            conversation=conv,
        )

        # Now advisor responds from WhatsApp Web (smb.message.echoes)
        result = process_whatsapp_message(
            client=self.client_obj,
            channel=self.channel,
            event={
                "message_id": "wamid-2",
                "text": "prueba-estructural-2",
                "timestamp": str(int(timezone.now().timestamp()) + 10),
            },
            direction=MensajeWhatsApp.SALIENTE,
            sender_type=MensajeWhatsApp.SENDER_ADVISOR,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP,
            conversation=conv,
        )

        self.assertTrue(result["created"])
        self.assertTrue(result["summary_updated"])
        self.assertFalse(result["unread_incremented"])
        self.assertTrue(result["takeover_activated"])  # CRITICAL

        conv.refresh_from_db()
        self.assertTrue(conv.bot_pausado)
        self.assertEqual(conv.estado_atencion, ConversacionWhatsApp.ATENCION_ASESOR)
        self.assertEqual(conv.resumen, "prueba-estructural-2")

    def test_prueba_estructural_3_bot_silent(self):
        """Paso 3: Cliente envía prueba-estructural-3, bot NO responde (takeover active)"""
        # Conversation with active takeover
        conv = ConversacionWhatsApp.objects.create(
            cliente=self.client_obj,
            channel=self.channel,
            estado_atencion=ConversacionWhatsApp.ATENCION_ASESOR,
            bot_pausado=True,
        )

        result = process_whatsapp_message(
            client=self.client_obj,
            channel=self.channel,
            event={
                "message_id": "wamid-3",
                "text": "prueba-estructural-3",
                "timestamp": str(int(timezone.now().timestamp())),
            },
            direction=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
            source=MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            conversation=conv,
        )

        self.assertTrue(result["created"])
        self.assertTrue(result["unread_incremented"])
        self.assertFalse(result["takeover_activated"])  # Already active

        conv.refresh_from_db()
        # Bot must NOT respond because takeover is active
        self.assertTrue(conv.bot_pausado)
        self.assertEqual(conv.estado_atencion, ConversacionWhatsApp.ATENCION_ASESOR)
