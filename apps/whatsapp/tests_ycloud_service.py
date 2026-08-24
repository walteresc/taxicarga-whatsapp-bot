"""Test YCloud service classification and message processing."""
from datetime import datetime
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.whatsapp.services_ycloud import YCloudMessageProcessor


class YCloudClassificationTests(TestCase):
    """Test event classification rules."""

    def setUp(self):
        self.processor = YCloudMessageProcessor()
        self.user = User.objects.create_user("testuser", "test@test.com", "pass")
        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="test_123",
            asesor=self.user,
            activo=True,
        )

    def test_inbound_classification(self):
        """Customer message should be: inbound, customer, whatsapp_customer."""
        event_data = {
            "from": "+51987654321",
            "wamid": "ycloud_msg_1",
            "text": "Hello",
            "timestamp": str(int(timezone.now().timestamp())),
        }

        classification = self.processor.classify_event(
            YCloudMessageProcessor.EVENT_INBOUND,
            event_data
        )

        self.assertEqual(classification["direction"], MensajeWhatsApp.ENTRANTE)
        self.assertEqual(classification["sender_type"], MensajeWhatsApp.SENDER_CUSTOMER)
        self.assertEqual(classification["source"], MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER)
        self.assertFalse(classification.get("human_intervention"))

    def test_echo_classification_advisor(self):
        """WhatsApp Web echo should be: outbound, advisor, whatsapp_business_app."""
        event_data = {
            "from": "+51987654321",
            "wamid": "ycloud_echo_1",
            "text": "Reply from Web",
            "timestamp": str(int(timezone.now().timestamp())),
        }

        classification = self.processor.classify_event(
            YCloudMessageProcessor.EVENT_ECHO,
            event_data
        )

        self.assertEqual(classification["direction"], MensajeWhatsApp.SALIENTE)
        self.assertEqual(classification["sender_type"], MensajeWhatsApp.SENDER_ADVISOR)
        self.assertEqual(classification["source"], MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP)
        self.assertTrue(classification.get("human_intervention"))

    def test_status_update_only(self):
        """Status update should return status_update_only flag."""
        event_data = {
            "wamid": "ycloud_msg_1",
            "status": "delivered",
        }

        classification = self.processor.classify_event(
            YCloudMessageProcessor.EVENT_STATUS,
            event_data
        )

        self.assertTrue(classification.get("status_update_only"))
        self.assertIsNone(classification.get("direction"))


class YCloudProcessingTests(TestCase):
    """Test full message processing pipeline."""

    def setUp(self):
        self.processor = YCloudMessageProcessor()
        self.user = User.objects.create_user("testuser", "test@test.com", "pass")
        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="test_123",
            asesor=self.user,
            activo=True,
        )

    def test_inbound_message_creates_conversation_and_message(self):
        """Inbound message should create conversation and message."""
        ts = timezone.make_aware(datetime(2026, 8, 21, 10, 0, 0))
        event_data = {
            "from": "+51999888777",
            "wamid": "ycloud_msg_001",
            "text": "First message",
            "timestamp": str(int(ts.timestamp())),
            "type": "text",
        }

        result = self.processor.process_ycloud_event(
            YCloudMessageProcessor.EVENT_INBOUND,
            event_data,
            self.channel,
        )

        self.assertTrue(result["created"])
        self.assertIsNotNone(result["message"])
        self.assertIsNotNone(result["conversation"])
        self.assertFalse(result.get("human_intervention"))

        # Verify in DB
        conv = result["conversation"]
        self.assertEqual(conv.cliente.telefono, "+51999888777")
        self.assertEqual(conv.ultima_actividad, ts)
        self.assertIn("First message", conv.resumen)
        self.assertEqual(conv.bot_pausado, False)
        self.assertEqual(conv.estado_atencion, ConversacionWhatsApp.ATENCION_BOT)

    def test_second_message_updates_ultima_actividad(self):
        """Second message should update ultima_actividad to new timestamp."""
        # First message at 10:00
        ts1 = timezone.make_aware(datetime(2026, 8, 21, 10, 0, 0))
        event1 = {
            "from": "+51999888777",
            "wamid": "ycloud_msg_001",
            "text": "First",
            "timestamp": str(int(ts1.timestamp())),
        }

        result1 = self.processor.process_ycloud_event(
            YCloudMessageProcessor.EVENT_INBOUND,
            event1,
            self.channel,
        )
        conv = result1["conversation"]

        # Second message at 11:30
        ts2 = timezone.make_aware(datetime(2026, 8, 21, 11, 30, 0))
        event2 = {
            "from": "+51999888777",
            "wamid": "ycloud_msg_002",
            "text": "Second",
            "timestamp": str(int(ts2.timestamp())),
        }

        result2 = self.processor.process_ycloud_event(
            YCloudMessageProcessor.EVENT_INBOUND,
            event2,
            self.channel,
        )
        conv = result2["conversation"]
        conv.refresh_from_db()

        # Verify timestamp updated
        self.assertEqual(conv.ultima_actividad, ts2)
        self.assertIn("Second", conv.resumen)

    def test_human_takeover_detected(self):
        """Echo from WhatsApp Web should set bot_pausado=True."""
        ts = timezone.make_aware(datetime(2026, 8, 21, 10, 0, 0))

        # First create a conversation with inbound message
        event_inbound = {
            "from": "+51999888777",  # Customer phone
            "to": "",  # No 'to' in inbound
            "wamid": "ycloud_msg_001",
            "text": "Customer message",
            "timestamp": str(int(ts.timestamp())),
        }

        result1 = self.processor.process_ycloud_event(
            YCloudMessageProcessor.EVENT_INBOUND,
            event_inbound,
            self.channel,
        )
        conv = result1["conversation"]
        conv.refresh_from_db()

        self.assertEqual(conv.bot_pausado, False)
        self.assertEqual(conv.estado_atencion, ConversacionWhatsApp.ATENCION_BOT)

        # Now send REAL echo from WhatsApp Web (advisor intervention)
        # In YCloud echo: from=business, to=customer
        ts2 = timezone.make_aware(datetime(2026, 8, 21, 10, 5, 0))
        event_echo = {
            "from": "51999999999",  # Business number (Lima Express channel)
            "to": "+51999888777",  # Customer phone (MUST be 'to' in echo)
            "wamid": "ycloud_echo_001",
            "text": "Advisor reply from Web",
            "timestamp": str(int(ts2.timestamp())),
        }

        result2 = self.processor.process_ycloud_event(
            YCloudMessageProcessor.EVENT_ECHO,
            event_echo,
            self.channel,
        )

        self.assertTrue(result2["human_intervention"], "Echo should set human_intervention=True")

        # Verify message created with correct classification
        message = result2.get("message")
        self.assertIsNotNone(message)
        self.assertEqual(message.sender_type, MensajeWhatsApp.SENDER_ADVISOR)
        self.assertEqual(message.direccion, MensajeWhatsApp.SALIENTE)
        self.assertEqual(message.source, MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP)

        # Verify conversation state changed
        conv.refresh_from_db()
        self.assertTrue(conv.bot_pausado, "Echo should set bot_pausado=True")
        self.assertEqual(conv.estado_atencion, ConversacionWhatsApp.ATENCION_ASESOR)

        # Verify no unread increment (echo is outbound)
        # Assuming unread only increments for inbound
        messages = conv.mensajes.all()
        self.assertEqual(messages.count(), 2)  # One inbound, one echo

    def test_idempotent_by_wamid(self):
        """Same wamid should not create duplicate messages."""
        ts = timezone.make_aware(datetime(2026, 8, 21, 10, 0, 0))
        event_data = {
            "from": "+51999888777",
            "wamid": "ycloud_msg_dup",
            "text": "Message",
            "timestamp": str(int(ts.timestamp())),
        }

        # Process twice with same wamid
        result1 = self.processor.process_ycloud_event(
            YCloudMessageProcessor.EVENT_INBOUND,
            event_data,
            self.channel,
        )
        self.assertTrue(result1["created"])

        result2 = self.processor.process_ycloud_event(
            YCloudMessageProcessor.EVENT_INBOUND,
            event_data,
            self.channel,
        )
        self.assertFalse(result2["created"])

        # Only one message should exist
        conv = result2["conversation"]
        count = conv.mensajes.filter(meta_message_id="ycloud_msg_dup").count()
        self.assertEqual(count, 1)
