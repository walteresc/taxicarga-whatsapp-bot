import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.cotizador.delivery import enviar_revision_whatsapp
from apps.cotizador.models import CotizacionComercial, EnvioCotizacion, RevisionCotizacion
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel
from apps.integrations.models import ConversationControl, IntegrationOutboxEvent
from apps.integrations.services.meta_sender import process_meta_outbox_event
from apps.whatsapp.utils import extract_event


class WhatsAppRealDeliveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        cls.user = get_user_model().objects.create_user("stage9_advisor", password="x")
        cls.user.groups.add(group)
        cls.channel = WhatsAppChannel.objects.create(nombre="Stage 9", phone_number_id="phone-stage9")
        cls.customer = Cliente.objects.create(nombre="Cliente Stage 9", telefono="51955550009")
        cls.lead = Lead.objects.create(cliente=cls.customer, whatsapp_channel=cls.channel)
        cls.conversation = ConversacionWhatsApp.objects.create(
            cliente=cls.customer, lead=cls.lead, channel=cls.channel,
        )
        ConversationControl.objects.get_or_create(conversation=cls.conversation)

    def setUp(self):
        self.quote = CotizacionComercial.objects.create(
            codigo=f"COT-ST9-{CotizacionComercial.objects.count()}", lead=self.lead,
            channel=self.channel, origen="asesor", asesor=self.user,
        )
        self.revision = RevisionCotizacion.objects.create(
            cotizacion=self.quote, numero=1, creada_por=self.user,
            precio_final=500, mensaje_whatsapp="Cotización lista: S/ 500",
        )

    @override_settings(META_OUTBOX_ENABLED=True, CHATWOOT_AGENT_TO_WHATSAPP_ENABLED=True, CHATWOOT_STAGE7_TEST_CHANNEL_ID="1")
    def test_send_persists_meta_id_and_closes_draft(self):
        send = self._sender({"messages": [{"id": "wamid.stage9.sent"}]})
        envio = enviar_revision_whatsapp(self.revision.id, actor=self.user)
        result = process_meta_outbox_event(envio.outbox_event_id, sender=send)
        envio.refresh_from_db()
        self.assertEqual(envio.estado, "enviado")
        self.assertEqual(envio.meta_message_id, "wamid.stage9.sent")
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.estado, "enviada")
        self.assertTrue(result.sent)
        self.assertEqual(send.call_count, 1)

    @override_settings(META_OUTBOX_ENABLED=True, CHATWOOT_AGENT_TO_WHATSAPP_ENABLED=True, CHATWOOT_STAGE7_TEST_CHANNEL_ID="1")
    def test_failure_is_persistent_and_schedules_retry(self):
        send = self._sender({"sent": False, "reason": "request_error", "status_code": 503})
        envio = enviar_revision_whatsapp(self.revision.id, actor=self.user)
        process_meta_outbox_event(envio.outbox_event_id, sender=send)
        envio.refresh_from_db()
        self.assertEqual(envio.estado, "error")
        self.assertEqual(envio.error_codigo, "http_503")
        self.assertIsNotNone(envio.proximo_reintento)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.estado, "borrador")

    def test_meta_delivery_and_read_statuses_update_attempt(self):
        envio = EnvioCotizacion.objects.create(
            revision=self.revision, channel=self.channel,
            estado="enviado", meta_message_id="wamid.stage9.status",
        )
        for status in ("delivered", "read"):
            payload = {"entry": [{"changes": [{"value": {"statuses": [{
                "id": envio.meta_message_id, "status": status, "timestamp": "1786120000"
            }]}}]}]}
            response = self.client.post(
                reverse("whatsapp-webhook"), data=json.dumps(payload), content_type="application/json"
            )
            self.assertEqual(response.status_code, 200)
        envio.refresh_from_db()
        self.assertEqual(envio.estado, "leido")
        self.assertIsNotNone(envio.entregado_en)
        self.assertIsNotNone(envio.leido_en)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.estado, "entregada")

    def test_detail_send_action_uses_outbox_without_http(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("dashboard-whatsapp-cotizacion-accion", args=[self.quote.id]),
            {"action": "send", "next": "detail"},
        )
        self.assertRedirects(response, reverse("dashboard-whatsapp-cotizacion-detalle", args=[self.quote.id]))
        self.assertTrue(self.revision.envios.filter(outbox_event__event_type="send_commercial_quote").exists())

    @staticmethod
    def _sender(result):
        from unittest.mock import Mock
        return Mock(return_value=result)

    def test_extracts_document_and_location_payloads(self):
        def payload(message):
            return {"entry": [{"changes": [{"value": {
                "metadata": {"phone_number_id": self.channel.phone_number_id},
                "messages": [message],
            }}]}]}
        document = extract_event(payload({
            "from": self.customer.telefono, "id": "doc-1", "type": "document",
            "document": {"id": "media-doc", "mime_type": "application/pdf", "caption": "Lista"},
        }))
        location = extract_event(payload({
            "from": self.customer.telefono, "id": "loc-1", "type": "location",
            "location": {"latitude": -12.1, "longitude": -77.0},
        }))
        self.assertEqual(document["media_id"], "media-doc")
        self.assertEqual(document["caption"], "Lista")
        self.assertEqual(location["text"], "-12.1,-77.0")
