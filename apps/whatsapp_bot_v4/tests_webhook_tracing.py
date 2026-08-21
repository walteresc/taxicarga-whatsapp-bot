"""
Test para rastrear exactamente qué funciones se invocan cuando llega un webhook YCloud real.

Usamos mocks/spies para interceptar llamadas sin cambiar el código.
"""

from django.test import TestCase, Client
from django.utils import timezone
from unittest.mock import patch, MagicMock, call
import json

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp_bot_v4.models import WebhookEvent


class YCloudWebhookTracingTests(TestCase):
    """Rastrear ejecución del webhook real."""

    def setUp(self):
        self.client = Client()
        self.webhook_url = "/webhooks/ycloud/v1/"

    def test_trace_real_ycloud_event_execution_path(self):
        """Rastrear qué funciones se ejecutan para un evento inbound real."""

        # Payload tipo real de YCloud (inbound message)
        payload = {
            "id": "evt_6a88b86717f91b38de657a64",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "6a88b867b14c5b324b537db9",
                "from": "51995403320",
                "fromName": "Walter Escobar",
                "text": {
                    "body": "FASE5A-WEBHOOK-TRACE-001"
                }
            },
            "timestamp": int(timezone.now().timestamp())
        }

        # Spies en funciones críticas
        with patch('apps.whatsapp_bot_v4.services.ycloud_webhook_service.handle_inbound_message') as mock_handle_inbound, \
             patch('apps.whatsapp_bot_v4.services.ycloud_webhook_service.verify_ycloud_signature') as mock_verify, \
             patch('apps.clientes.models.Cliente.objects.get_or_create') as mock_get_or_create_cliente:

            # Setup
            mock_verify.return_value = True
            test_cliente = Cliente.objects.create(telefono="+51995403320", nombre="Walter Test")
            mock_get_or_create_cliente.return_value = (test_cliente, False)

            # POST al webhook
            resp = self.client.post(
                self.webhook_url,
                data=json.dumps(payload),
                content_type='application/json',
                HTTP_X_YCLOUD_SIGNATURE='mock-signature'
            )

            # Verificar respuesta
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()['status'], 'ok')

            # Verificar que se llamó handle_inbound_message
            mock_handle_inbound.assert_called_once()
            call_args = mock_handle_inbound.call_args[0][0]
            self.assertEqual(call_args.get('type'), 'whatsapp.inbound_message.received')

    def test_trace_mensaje_creation_without_conversation_update(self):
        """
        Verificar si el webhook crea el mensaje pero NO actualiza
        ultima_actividad ni resumen de la conversación.
        """
        # Setup
        cliente = Cliente.objects.create(telefono="+51995403320", nombre="Walter Test")
        conv_old = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            estado_atencion="bot"
        )
        # Fijar times old
        conv_old.ultima_actividad = timezone.now() - timezone.timedelta(days=1)
        conv_old.resumen = "old-message"
        conv_old.save()

        payload = {
            "id": "evt_trace_002",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_trace_002",
                "from": "51995403320",
                "fromName": "Walter Test",
                "text": {
                    "body": "NEW-MESSAGE-FOR-TRACE"
                }
            },
            "timestamp": int(timezone.now().timestamp())
        }

        with patch('apps.whatsapp_bot_v4.services.ycloud_webhook_service.verify_ycloud_signature') as mock_verify, \
             patch('apps.whatsapp_bot_v4.services.ycloud_webhook_service.can_bot_respond') as mock_can_respond, \
             patch('apps.whatsapp_bot_v4.services.ycloud_webhook_service.process_bot_response') as mock_process_bot:

            mock_verify.return_value = True
            mock_can_respond.return_value = False  # Bot no responde, pero mensaje se debe guardar

            resp = self.client.post(
                self.webhook_url,
                data=json.dumps(payload),
                content_type='application/json',
                HTTP_X_YCLOUD_SIGNATURE='mock'
            )

            # Verificar respuesta
            self.assertEqual(resp.status_code, 200)

            # Verificar mensaje fue creado
            msg = MensajeWhatsApp.objects.filter(meta_message_id='wamid_trace_002').first()
            self.assertIsNotNone(msg)
            self.assertEqual(msg.contenido, "NEW-MESSAGE-FOR-TRACE")

            # VERIFICACIÓN CRÍTICA: ¿Se actualizó ultima_actividad?
            conv_refreshed = ConversacionWhatsApp.objects.get(pk=conv_old.id)
            print(f"\n[TRACING] Conversación {conv_old.id}:")
            print(f"  antes: ua={conv_old.ultima_actividad}, resumen={conv_old.resumen}")
            print(f"  después: ua={conv_refreshed.ultima_actividad}, resumen={conv_refreshed.resumen}")
            print(f"  mensaje fecha: {msg.fecha_mensaje}")

            # El test actual revelará si se actualizó o no
            if conv_refreshed.ultima_actividad != conv_old.ultima_actividad:
                print(f"  ✓ ultima_actividad SÍ se actualizó")
            else:
                print(f"  ✗ ultima_actividad NO se actualizó")

            if conv_refreshed.resumen != conv_old.resumen:
                print(f"  ✓ resumen SÍ se actualizó")
            else:
                print(f"  ✗ resumen NO se actualizó")

    def test_webhook_event_idempotency_check(self):
        """Verificar que WebhookEvent registra el evento para idempotencia."""

        payload = {
            "id": "evt_idempotent_test",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_idempotent",
                "from": "51995403320",
                "fromName": "Walter",
                "text": {"body": "test"}
            },
            "timestamp": int(timezone.now().timestamp())
        }

        with patch('apps.whatsapp_bot_v4.services.ycloud_webhook_service.verify_ycloud_signature') as m_verify:
            m_verify.return_value = True

            # Primera ejecución
            resp1 = self.client.post(
                self.webhook_url,
                data=json.dumps(payload),
                content_type='application/json',
                HTTP_X_YCLOUD_SIGNATURE='mock'
            )
            self.assertEqual(resp1.status_code, 200)

            # Verificar que WebhookEvent fue registrado
            event1 = WebhookEvent.objects.filter(
                source='ycloud',
                external_message_id='evt_idempotent_test'
            ).first()
            self.assertIsNotNone(event1)

            # Segunda ejecución (duplicado)
            resp2 = self.client.post(
                self.webhook_url,
                data=json.dumps(payload),
                content_type='application/json',
                HTTP_X_YCLOUD_SIGNATURE='mock'
            )
            self.assertEqual(resp2.status_code, 200)
            # Debe retornar 'skipped' o 'ok' sin procesar de nuevo
            result = resp2.json()
            print(f"\n[IDEMPOTENCY] Segunda ejecución retornó: {result}")
            # Si retorna 'skipped', la idempotencia funciona a nivel webhook event

