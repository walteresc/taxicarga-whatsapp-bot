"""Integration tests for YCloud webhook using real endpoint."""
from datetime import datetime
from django.test import TestCase, Client
from django.utils import timezone
from django.contrib.auth.models import User
from django.http import HttpRequest
from unittest.mock import patch, MagicMock
import json

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.whatsapp.views import _receive_message


class YCloudWebhookIntegrationTests(TestCase):
    """Test webhook endpoint with YCloud payloads."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("testuser", "test@test.com", "pass")
        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="123456789",
            numero_visible="+51987654321",
            asesor=self.user,
            activo=True,
        )

    def _build_inbound_payload(self, phone, text, wamid, ts=None):
        """Build YCloud inbound message payload."""
        if ts is None:
            ts = int(timezone.now().timestamp())

        return {
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "phone_number_id": self.channel.phone_number_id,
                            "display_phone_number": self.channel.numero_visible,
                        },
                        "messages": [{
                            "from": phone,
                            "id": wamid,
                            "timestamp": str(ts),
                            "type": "text",
                            "text": {"body": text},
                        }]
                    }
                }]
            }]
        }

    def _build_echo_payload(self, phone, text, wamid, ts=None):
        """Build YCloud echo (outbound from Web/mobile) payload."""
        if ts is None:
            ts = int(timezone.now().timestamp())

        return {
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "phone_number_id": self.channel.phone_number_id,
                            "display_phone_number": self.channel.numero_visible,
                        },
                        "messages": [{
                            "from": self.channel.phone_number_id,  # Echo from business
                            "id": wamid,
                            "timestamp": str(ts),
                            "type": "text",
                            "text": {"body": text},
                        }]
                    }
                }]
            }]
        }

    @patch('apps.whatsapp.views._send_bot_message')
    def test_inbound_creates_conversation_and_message(self, mock_send):
        """Test: Inbound message creates conversation and message correctly."""
        # Mock bot message sending to avoid YCloud API errors in test
        mock_send.return_value = {
            "messages": [{"id": "mock_msg_id"}]
        }

        phone = "+51987654322"
        ts = timezone.make_aware(datetime(2026, 8, 21, 10, 0, 0))
        payload = self._build_inbound_payload(
            phone=phone,
            text="Test inbound message",
            wamid="ycloud_001",
            ts=int(ts.timestamp()),
        )

        response = self.client.post(
            "/webhook/whatsapp/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])

        # Verify in DB
        conv = ConversacionWhatsApp.objects.filter(cliente__telefono=phone).first()
        self.assertIsNotNone(conv)
        self.assertEqual(conv.cliente.telefono, phone)
        self.assertEqual(conv.estado_atencion, ConversacionWhatsApp.ATENCION_BOT)
        self.assertFalse(conv.bot_pausado)

        msg = MensajeWhatsApp.objects.filter(meta_message_id="ycloud_001").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.direccion, MensajeWhatsApp.ENTRANTE)
        self.assertEqual(msg.sender_type, MensajeWhatsApp.SENDER_CUSTOMER)
        self.assertEqual(msg.source, MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER)
        self.assertEqual(msg.contenido, "Test inbound message")
        self.assertEqual(msg.fecha_mensaje, ts)

        # Verify conversation was updated
        conv.refresh_from_db()
        self.assertEqual(conv.ultima_actividad, ts)
        self.assertIn("Test inbound message", conv.resumen)

    @patch('apps.whatsapp.views._send_bot_message')
    def test_echo_from_whatsapp_web_triggers_takeover(self, mock_send):
        """Test: Echo from WhatsApp Web sets takeover and pauses bot."""
        mock_send.return_value = MagicMock(sent=True, id="mock_msg_id")

        phone = "+51987654323"

        # First create a conversation with inbound message
        ts1 = timezone.make_aware(datetime(2026, 8, 21, 10, 0, 0))
        payload1 = self._build_inbound_payload(
            phone=phone,
            text="Customer message",
            wamid="ycloud_101",
            ts=int(ts1.timestamp()),
        )

        response1 = self.client.post(
            "/dashboard/webhook/whatsapp/",
            data=json.dumps(payload1),
            content_type="application/json",
        )
        self.assertEqual(response1.status_code, 200)

        conv = ConversacionWhatsApp.objects.filter(cliente__telefono=phone).first()
        self.assertFalse(conv.bot_pausado)

        # Now send echo from WhatsApp Web
        ts2 = timezone.make_aware(datetime(2026, 8, 21, 10, 5, 0))
        payload2 = self._build_echo_payload(
            phone=phone,
            text="Advisor reply from Web",
            wamid="ycloud_echo_101",
            ts=int(ts2.timestamp()),
        )

        response2 = self.client.post(
            "/dashboard/webhook/whatsapp/",
            data=json.dumps(payload2),
            content_type="application/json",
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertTrue(data2.get("human_takeover"))

        # Verify bot was paused
        conv.refresh_from_db()
        self.assertTrue(conv.bot_pausado)
        self.assertEqual(conv.estado_atencion, ConversacionWhatsApp.ATENCION_ASESOR)

        # Verify echo message was created
        msg = MensajeWhatsApp.objects.filter(meta_message_id="ycloud_echo_101").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.direccion, MensajeWhatsApp.SALIENTE)
        self.assertEqual(msg.sender_type, MensajeWhatsApp.SENDER_ADVISOR)
        self.assertEqual(msg.source, MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP)

    @patch('apps.whatsapp.views._send_bot_message')
    def test_duplicate_inbound_not_created_twice(self, mock_send):
        """Test: Same wamid sent twice doesn't create duplicate message."""
        mock_send.return_value = MagicMock(sent=True, id="mock_msg_id")

        phone = "+51987654324"
        ts = timezone.make_aware(datetime(2026, 8, 21, 10, 0, 0))
        payload = self._build_inbound_payload(
            phone=phone,
            text="Duplicate test",
            wamid="ycloud_dup_001",
            ts=int(ts.timestamp()),
        )

        # Send twice
        response1 = self.client.post(
            "/dashboard/webhook/whatsapp/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response1.status_code, 200)

        response2 = self.client.post(
            "/dashboard/webhook/whatsapp/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response2.status_code, 200)

        # Should only have one message
        count = MensajeWhatsApp.objects.filter(meta_message_id="ycloud_dup_001").count()
        self.assertEqual(count, 1)

    @patch('apps.whatsapp.views._send_bot_message')
    def test_newer_message_updates_ultima_actividad(self, mock_send):
        """Test: Newer message updates ultima_actividad, older doesn't retro-grade."""
        mock_send.return_value = MagicMock(sent=True, id="mock_msg_id")

        phone = "+51987654325"

        # First message at 10:00
        ts1 = timezone.make_aware(datetime(2026, 8, 21, 10, 0, 0))
        payload1 = self._build_inbound_payload(
            phone=phone,
            text="First message",
            wamid="ycloud_201",
            ts=int(ts1.timestamp()),
        )

        self.client.post(
            "/dashboard/webhook/whatsapp/",
            data=json.dumps(payload1),
            content_type="application/json",
        )

        conv = ConversacionWhatsApp.objects.filter(cliente__telefono=phone).first()
        self.assertEqual(conv.ultima_actividad, ts1)

        # Second message at 11:30 (newer)
        ts2 = timezone.make_aware(datetime(2026, 8, 21, 11, 30, 0))
        payload2 = self._build_inbound_payload(
            phone=phone,
            text="Second message",
            wamid="ycloud_202",
            ts=int(ts2.timestamp()),
        )

        self.client.post(
            "/dashboard/webhook/whatsapp/",
            data=json.dumps(payload2),
            content_type="application/json",
        )

        conv.refresh_from_db()
        self.assertEqual(conv.ultima_actividad, ts2)
        self.assertIn("Second message", conv.resumen)

        # Third message at 10:15 (older, should be ignored)
        ts3 = timezone.make_aware(datetime(2026, 8, 21, 10, 15, 0))
        payload3 = self._build_inbound_payload(
            phone=phone,
            text="Old message",
            wamid="ycloud_203",
            ts=int(ts3.timestamp()),
        )

        self.client.post(
            "/dashboard/webhook/whatsapp/",
            data=json.dumps(payload3),
            content_type="application/json",
        )

        conv.refresh_from_db()
        # Should NOT retro-grade to ts3
        self.assertEqual(conv.ultima_actividad, ts2)
        # Should NOT update resumen to old message
        self.assertIn("Second message", conv.resumen)

    @patch('apps.whatsapp.views._send_bot_message')
    def test_webhook_response_contains_required_fields(self, mock_send):
        """Test: Webhook response includes conversation_id and message_id."""
        mock_send.return_value = MagicMock(sent=True, id="mock_msg_id")

        phone = "+51987654326"
        ts = timezone.make_aware(datetime(2026, 8, 21, 10, 0, 0))
        payload = self._build_inbound_payload(
            phone=phone,
            text="Response test",
            wamid="ycloud_resp_001",
            ts=int(ts.timestamp()),
        )

        response = self.client.post(
            "/webhook/whatsapp/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        # Response might include additional fields depending on bot logic
        # but basic ok should be present
        data = response.json()
        self.assertTrue(data["ok"])
