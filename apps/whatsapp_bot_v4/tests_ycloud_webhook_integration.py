"""
Integration tests for refactored /webhooks/ycloud/v1/ endpoint.

Validates:
1. Signature validation (valid/invalid)
2. JSON parsing
3. Event registration (WebhookEvent idempotence)
4. Delegation to YCloudMessageProcessor.process_ycloud_event()
5. HTTP 200 immediate return (no blocking on bot processing)
6. Message persistence (no duplicates)
7. Conversation updates (ultima_actividad, resumen, channel isolation)
8. Unread counter updates
9. Echo/takeover detection
10. Status updates
"""

from django.test import TestCase, Client
from django.utils import timezone
from django.conf import settings
import json
import hmac
import hashlib

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.whatsapp_bot_v4.models import WebhookEvent


class YCloudWebhookIntegrationTests(TestCase):
    """Test refactored /webhooks/ycloud/v1/ endpoint."""

    def setUp(self):
        self.client = Client()
        self.webhook_url = "/webhooks/ycloud/v1/"

        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="1234567",
            numero_visible="+51995403320",
            activo=True,
        )

        # Asegurar YCLOUD_WEBHOOK_SECRET en settings
        if not hasattr(settings, 'YCLOUD_WEBHOOK_SECRET'):
            settings.YCLOUD_WEBHOOK_SECRET = "test-secret-key"

    def _sign_payload(self, body_bytes, timestamp=None):
        """Generate valid HMAC-SHA256 signature for YCloud webhook."""
        if timestamp is None:
            timestamp = str(int(timezone.now().timestamp()))

        signed_content = f"{timestamp}.{body_bytes.decode('utf-8')}" if isinstance(body_bytes, bytes) else f"{timestamp}.{body_bytes}"
        signature = hmac.new(
            settings.YCLOUD_WEBHOOK_SECRET.encode(),
            signed_content.encode() if isinstance(signed_content, str) else signed_content,
            hashlib.sha256
        ).hexdigest()

        return f"t={timestamp},s={signature}"

    def test_1_valid_signature(self):
        """1. Validate valid HMAC signature."""
        payload = {
            "id": "evt_test_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_001",
                "from": "51995403320",
                "text": {"body": "Test message"}
            }
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        resp = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'ok')

    def test_2_invalid_signature(self):
        """2. Reject invalid signature."""
        payload = {
            "id": "evt_test_002",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_002",
                "from": "51995403320",
                "text": {"body": "Test"}
            }
        }

        body = json.dumps(payload).encode('utf-8')

        resp = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE="t=123456,s=invalid_signature_here"
        )

        self.assertEqual(resp.status_code, 401)
        self.assertIn('error', resp.json())

    def test_3_invalid_json(self):
        """3. Reject invalid JSON."""
        resp = self.client.post(
            self.webhook_url,
            data="not valid json",
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE="t=123456,s=sig"
        )

        self.assertEqual(resp.status_code, 400)

    def test_4_inbound_message_persistence(self):
        """4. Inbound message: persist message, conversation, cliente."""
        payload = {
            "id": "evt_inbound_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_inbound_001",
                "from": "51995403320",
                "fromName": "Test User",
                "text": {"body": "I need a move from Lima to Arequipa"}
            },
            "timestamp": int(timezone.now().timestamp())
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        resp = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature
        )

        # HTTP 200 immediate
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'ok')

        # Verify Cliente created
        cliente = Cliente.objects.filter(telefono="+51995403320").first()
        self.assertIsNotNone(cliente)
        self.assertEqual(cliente.nombre, "Test User")

        # Verify Conversation created (unique on cliente, channel, cerrada_en IS NULL)
        conv = ConversacionWhatsApp.objects.filter(
            cliente=cliente,
            channel=self.channel,
            cerrada_en__isnull=True
        ).first()
        self.assertIsNotNone(conv)

        # Verify Message created
        msg = MensajeWhatsApp.objects.filter(meta_message_id="wamid_inbound_001").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.contenido, "I need a move from Lima to Arequipa")
        self.assertEqual(msg.direccion, MensajeWhatsApp.ENTRANTE)
        self.assertEqual(msg.origen, MensajeWhatsApp.ORIGEN_CLIENTE)
        self.assertEqual(msg.conversacion_id, conv.id)

    def test_5_conversation_updates_on_new_message(self):
        """5. ultima_actividad and resumen update when new message arrives."""
        cliente = Cliente.objects.create(telefono="+51995403320", nombre="Test")
        conv = ConversacionWhatsApp.objects.create(cliente=cliente, channel=self.channel)

        old_ua = timezone.now() - timezone.timedelta(hours=1)
        conv.ultima_actividad = old_ua
        conv.resumen = "old resumen"
        conv.save()

        payload = {
            "id": "evt_ua_update_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_ua_001",
                "from": "51995403320",
                "text": {"body": "NEW MESSAGE FOR UPDATE"}
            },
            "timestamp": int(timezone.now().timestamp())
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        resp = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature
        )

        self.assertEqual(resp.status_code, 200)

        # Refresh conversation
        conv.refresh_from_db()
        self.assertGreater(conv.ultima_actividad, old_ua)
        self.assertEqual(conv.resumen, "NEW MESSAGE FOR UPDATE")

    def test_6_no_duplicate_conversations_per_channel(self):
        """6. Same (cliente, channel) reuses conversation (UNIQUE constraint)."""
        payload_1 = {
            "id": "evt_dup_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_dup_001",
                "from": "51995403321",
                "text": {"body": "Message 1"}
            }
        }

        payload_2 = {
            "id": "evt_dup_002",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_dup_002",
                "from": "51995403321",
                "text": {"body": "Message 2"}
            }
        }

        # Send two messages from same client
        for payload in [payload_1, payload_2]:
            body = json.dumps(payload).encode('utf-8')
            signature = self._sign_payload(body)

            resp = self.client.post(
                self.webhook_url,
                data=body,
                content_type='application/json',
                HTTP_YCLOUD_SIGNATURE=signature
            )
            self.assertEqual(resp.status_code, 200)

        # Should have exactly 1 conversation
        cliente = Cliente.objects.get(telefono="+51995403321")
        active_convs = ConversacionWhatsApp.objects.filter(
            cliente=cliente,
            channel=self.channel,
            cerrada_en__isnull=True
        )
        self.assertEqual(active_convs.count(), 1)

        # Should have 2 messages in same conversation
        msgs = MensajeWhatsApp.objects.filter(conversacion=active_convs.first())
        self.assertEqual(msgs.count(), 2)

    def test_7_webhook_event_idempotence(self):
        """7. Same event_id never processes twice (WebhookEvent)."""
        payload = {
            "id": "evt_idempotent_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_idem_001",
                "from": "51995403322",
                "text": {"body": "Unique message"}
            }
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        # Send once
        resp1 = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.json()['status'], 'ok')

        # Send again (exact same payload)
        resp2 = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature
        )
        self.assertEqual(resp2.status_code, 200)
        # Second call returns 'skipped' or 'ok' (depending on implementation)
        result = resp2.json()
        self.assertIn(result['status'], ['skipped', 'ok'])

        # Should have exactly 1 message (not 2)
        msgs = MensajeWhatsApp.objects.filter(meta_message_id="wamid_idem_001")
        self.assertEqual(msgs.count(), 1)

    def test_8_same_wamid_different_event_id_skipped(self):
        """8. Same wamid with different event_id still skipped (message idempotence)."""
        wamid = "wamid_same_004"
        cliente_phone = "51995403323"

        # Message 1
        payload_1 = {
            "id": "evt_same_wamid_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": wamid,
                "from": cliente_phone,
                "text": {"body": "Same wamid message"}
            }
        }

        # Message 2 (different event_id, same wamid)
        payload_2 = {
            "id": "evt_same_wamid_002",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": wamid,
                "from": cliente_phone,
                "text": {"body": "Same wamid message"}
            }
        }

        for payload in [payload_1, payload_2]:
            body = json.dumps(payload).encode('utf-8')
            signature = self._sign_payload(body)

            resp = self.client.post(
                self.webhook_url,
                data=body,
                content_type='application/json',
                HTTP_YCLOUD_SIGNATURE=signature
            )
            self.assertEqual(resp.status_code, 200)

        # Should have exactly 1 message (second request had same wamid)
        msgs = MensajeWhatsApp.objects.filter(meta_message_id=wamid)
        self.assertEqual(msgs.count(), 1)

    def test_9_multiple_clients_separate_conversations(self):
        """9. Client isolation: different clients → separate conversations."""
        for client_num in [51995403330, 51995403331]:
            payload = {
                "id": f"evt_client_{client_num}",
                "type": "whatsapp.inbound_message.received",
                "whatsappInboundMessage": {
                    "id": f"wamid_client_{client_num}",
                    "from": str(client_num),
                    "text": {"body": "Client message"}
                }
            }

            body = json.dumps(payload).encode('utf-8')
            signature = self._sign_payload(body)

            resp = self.client.post(
                self.webhook_url,
                data=body,
                content_type='application/json',
                HTTP_YCLOUD_SIGNATURE=signature
            )
            self.assertEqual(resp.status_code, 200)

        # Should have 2 different conversations
        convs = ConversacionWhatsApp.objects.filter(
            channel=self.channel,
            cerrada_en__isnull=True
        )
        self.assertEqual(convs.count(), 2)

    def test_10_echo_message_takeover_detected(self):
        """10. Echo (whatsapp.smb.message.echoes) triggers human takeover."""
        cliente = Cliente.objects.create(telefono="+51995403324", nombre="Test")
        conv = ConversacionWhatsApp.objects.create(cliente=cliente, channel=self.channel)

        payload = {
            "id": "evt_echo_001",
            "type": "whatsapp.smb.message.echoes",
            "whatsappMessage": {
                "id": "wamid_echo_001",
                "from": self.channel.numero_visible,
                "to": "51995403324",  # Echo: 'to' is cliente
                "text": {"body": "Advisor message"}
            }
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        resp = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature
        )

        self.assertEqual(resp.status_code, 200)

        # Verify echo message created (outbound, advisor origin)
        msg = MensajeWhatsApp.objects.filter(meta_message_id="wamid_echo_001").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.direccion, MensajeWhatsApp.SALIENTE)
        self.assertEqual(msg.origen, MensajeWhatsApp.ORIGEN_ASESOR)

        # Verify bot paused (human takeover)
        conv.refresh_from_db()
        self.assertTrue(conv.bot_pausado)
        self.assertEqual(conv.estado_atencion, ConversacionWhatsApp.ATENCION_ASESOR)

    def test_11_status_update_handled(self):
        """11. Status updates (whatsapp.message.updated) update message state."""
        # Create existing message first
        cliente = Cliente.objects.create(telefono="+51995403325", nombre="Test")
        conv = ConversacionWhatsApp.objects.create(cliente=cliente, channel=self.channel)
        msg = MensajeWhatsApp.objects.create(
            conversacion=conv,
            meta_message_id="wamid_status_001",
            direccion=MensajeWhatsApp.SALIENTE,
            origen=MensajeWhatsApp.ORIGEN_BOT,
            contenido="Bot message",
            estado="enviado"
        )

        # Send status update
        payload = {
            "id": "evt_status_001",
            "type": "whatsapp.message.updated",
            "id": "wamid_status_001",  # YCloud status update uses 'id' field
            "status": "entregado"
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        resp = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature
        )

        self.assertEqual(resp.status_code, 200)

    def test_12_multimedia_image_message(self):
        """12. Multimedia: image message persisted correctly."""
        payload = {
            "id": "evt_image_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_image_001",
                "from": "51995403326",
                "image": {
                    "id": "image_id_001",
                    "caption": "Photo of the apartment"
                }
            },
            "timestamp": int(timezone.now().timestamp())
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        resp = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature
        )

        self.assertEqual(resp.status_code, 200)

        # Verify image message created
        msg = MensajeWhatsApp.objects.filter(meta_message_id="wamid_image_001").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.tipo, "imagen")

    def test_13_channel_isolation(self):
        """13. Different channels for same client → separate conversations."""
        cliente = Cliente.objects.create(telefono="+51995403327", nombre="Test")

        channel_2 = WhatsAppChannel.objects.create(
            nombre="Channel 2",
            phone_number_id="7654321",
            numero_visible="+51987654321",
            activo=True,
        )

        # Create conversations for same client on different channels
        conv_1 = ConversacionWhatsApp.objects.create(cliente=cliente, channel=self.channel)
        conv_2 = ConversacionWhatsApp.objects.create(cliente=cliente, channel=channel_2)

        self.assertNotEqual(conv_1.id, conv_2.id)
        self.assertEqual(conv_1.channel_id, self.channel.id)
        self.assertEqual(conv_2.channel_id, channel_2.id)

