"""
Integration tests for WhatsApp webhook and message processing.
Tests the complete flow from webhook receive to BD persistence and resumen update.
"""

from django.test import TestCase, Client, TransactionTestCase
from django.utils import timezone
from datetime import timedelta
import json
from unittest.mock import patch, MagicMock

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.integrations.models import ChannelIntegrationPolicy
from apps.leads.models import Lead


class WebhookIntegrationTest(TransactionTestCase):
    """Test complete webhook processing flow"""

    def setUp(self):
        """Setup test data"""
        # Create client Walter Escobar
        self.client_walter = Cliente.objects.create(
            nombre="Walter Escobar",
            telefono="+51995403320",
        )

        # Create channel
        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="1171095159415009",
            numero_visible="Test",
            activo=True,
        )

        # Enable integration
        ChannelIntegrationPolicy.objects.create(
            channel=self.channel,
            enabled=True,
        )

        # Create conversation with old message
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_walter,
            channel=self.channel,
            estado_atencion=ConversacionWhatsApp.ATENCION_BOT,
        )

        # Create old message (probando4)
        old_time = timezone.now() - timedelta(hours=1)
        self.old_message = MensajeWhatsApp.objects.create(
            conversacion=self.conversation,
            meta_message_id="old-wamid-1",
            direccion=MensajeWhatsApp.ENTRANTE,
            origen="cliente",
            tipo="texto",
            contenido="probando4",
            estado="recibido",
            sender_type="customer",
            fecha_mensaje=old_time,
        )

        # Set conversation to old message time
        self.conversation.ultima_actividad = old_time
        self.conversation.resumen = "probando4"
        self.conversation.save()

        self.client_http = Client()

    @patch('apps.whatsapp.views.should_bot_reply')
    @patch('apps.whatsapp.views.handle_incoming_message')
    def test_webhook_updates_summary_on_new_message(self, mock_handle, mock_should_bot):
        """New message should update conversation summary"""

        # Mock bot to not process (avoid IA call)
        mock_should_bot.return_value = False
        mock_handle.return_value = "mocked response"

        # Simulate webhook payload with probando5
        webhook_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "51967619238",
                                    "phone_number_id": "1171095159415009",  # Our channel
                                },
                                "messages": [
                                    {
                                        "from": "51995403320",
                                        "id": "new-wamid-probando5",
                                        "timestamp": str(int(timezone.now().timestamp())),
                                        "type": "text",
                                        "text": {
                                            "body": "probando5"
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        # Send webhook
        response = self.client_http.post(
            "/webhook/whatsapp/",
            data=json.dumps(webhook_payload),
            content_type="application/json"
        )

        # Verify webhook accepted
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))

        # Reload conversation
        self.conversation.refresh_from_db()

        # Verify summary was updated
        self.assertEqual(self.conversation.resumen, "probando5")
        self.assertGreater(self.conversation.ultima_actividad, self.old_message.fecha_mensaje)

        # Verify new message was created
        new_msg = MensajeWhatsApp.objects.get(meta_message_id="new-wamid-probando5")
        self.assertEqual(new_msg.contenido, "probando5")
        self.assertEqual(new_msg.conversacion_id, self.conversation.id)

    @patch('apps.whatsapp.views.should_bot_reply')
    def test_webhook_duplicate_message_not_duplicated(self, mock_should_bot):
        """Same wamid received twice should create message once"""

        mock_should_bot.return_value = False

        webhook_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "51967619238",
                                    "phone_number_id": "1171095159415009",
                                },
                                "messages": [
                                    {
                                        "from": "51995403320",
                                        "id": "duplicate-wamid",
                                        "timestamp": str(int(timezone.now().timestamp())),
                                        "type": "text",
                                        "text": {
                                            "body": "probando_duplicate"
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        # Send webhook twice
        response1 = self.client_http.post(
            "/webhook/whatsapp/",
            data=json.dumps(webhook_payload),
            content_type="application/json"
        )
        response2 = self.client_http.post(
            "/webhook/whatsapp/",
            data=json.dumps(webhook_payload),
            content_type="application/json"
        )

        # Both should return 200/ok
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)

        # But only one message should exist
        messages = MensajeWhatsApp.objects.filter(meta_message_id="duplicate-wamid")
        self.assertEqual(messages.count(), 1)

    @patch('apps.whatsapp.views.should_bot_reply')
    def test_webhook_old_message_not_retrocede_summary(self, mock_should_bot):
        """Old message arriving late should not go backwards"""

        mock_should_bot.return_value = False

        # Create new message first
        now_timestamp = int(timezone.now().timestamp())
        new_webhook = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "51967619238",
                                    "phone_number_id": "1171095159415009",
                                },
                                "messages": [
                                    {
                                        "from": "51995403320",
                                        "id": "new-wamid",
                                        "timestamp": str(now_timestamp),
                                        "type": "text",
                                        "text": {
                                            "body": "probando_new"
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        resp1 = self.client_http.post(
            "/webhook/whatsapp/",
            data=json.dumps(new_webhook),
            content_type="application/json"
        )

        self.assertEqual(resp1.status_code, 200)
        self.conversation.refresh_from_db()

        # Now send old message with timestamp 2+ hours in the past
        old_timestamp = now_timestamp - (2 * 3600)  # exactly 2 hours before
        old_webhook = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "51967619238",
                                    "phone_number_id": "1171095159415009",
                                },
                                "messages": [
                                    {
                                        "from": "51995403320",
                                        "id": "old-wamid-late",
                                        "timestamp": str(old_timestamp),
                                        "type": "text",
                                        "text": {
                                            "body": "probando_old_late"
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        resp2 = self.client_http.post(
            "/webhook/whatsapp/",
            data=json.dumps(old_webhook),
            content_type="application/json"
        )

        self.assertEqual(resp2.status_code, 200)

        # Verify old message was created (idempotence works)
        old_msg = MensajeWhatsApp.objects.get(meta_message_id="old-wamid-late")
        self.assertEqual(old_msg.contenido, "probando_old_late")

        # Reload and verify summary didn't go backwards
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.resumen, "probando_new", "resumen should stay on newer message")
