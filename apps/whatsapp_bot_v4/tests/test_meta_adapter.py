from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.cotizador.models import Cotizacion, SolicitudCotizacion
from apps.integrations.enums import OwnerState
from apps.integrations.models import ConversationControl
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel

from ..adapters.crm import CRMV4Adapter
from ..adapters.meta import MetaPayloadError, MetaV4Adapter, OutboundMessage
from ..models import BotConversationState, V4ChannelRoute
from ..repositories.state import DjangoBotStateRepository
from ..services.conversation_service import ConversationService
from ..services.meta_webhook_service import MetaWebhookV4Service
from ..services.persistent_conversation_service import PersistentConversationService
from .fakes import ScriptedAgent, output
from .meta_fakes import FakeMetaAdapter, RecordingChatwoot, http_response, meta_payload


class MetaAdapterTests(TestCase):
    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            nombre="Channel TEST V4", phone_number_id="meta-v4-test", activo=True
        )
        V4ChannelRoute.objects.create(channel=self.channel, enabled=True)

    def service(self, outputs, *, meta=None, chatwoot=None):
        agent = ScriptedAgent(outputs)
        chatwoot = chatwoot or RecordingChatwoot()
        persistent = PersistentConversationService(
            ConversationService(agent),
            DjangoBotStateRepository(),
            crm_adapter=CRMV4Adapter(),
            chatwoot_adapter=chatwoot,
        )
        return MetaWebhookV4Service(
            meta_adapter=meta or FakeMetaAdapter(),
            persistent_service=persistent,
            chatwoot_adapter=chatwoot,
        ), agent, chatwoot

    def test_01_valid_meta_text_inbound_parsed(self):
        inbound = MetaV4Adapter.parse_inbound(meta_payload())
        self.assertEqual((inbound.external_message_id, inbound.channel_id, inbound.customer_id), ("wamid.test.1", "meta-v4-test", "51911112222"))

    def test_02_invalid_payload_rejected_safely(self):
        with self.assertRaises(MetaPayloadError):
            MetaV4Adapter.parse_inbound({"bad": "payload"})

    def test_03_unsupported_event_ignored(self):
        self.assertIsNone(MetaV4Adapter.parse_inbound(meta_payload(message_type="image")))

    def test_04_phone_number_resolves_only_opted_in_channel(self):
        service, _, _ = self.service([output()])
        self.assertEqual(service._resolve_channel("meta-v4-test"), self.channel)
        self.channel.v4_route.enabled = False
        self.channel.v4_route.save(update_fields=["enabled"])
        self.assertIsNone(service._resolve_channel("meta-v4-test"))

    def test_05_customer_identity_reuses_conversation(self):
        service, _, _ = self.service([output(), output()])
        service.process_payload(meta_payload(wamid="wamid.identity.1"))
        service.process_payload(meta_payload(wamid="wamid.identity.2"))
        self.assertEqual(Cliente.objects.filter(telefono="51911112222").count(), 1)
        self.assertEqual(ConversacionWhatsApp.objects.count(), 1)

    def test_06_duplicate_wamid_ignored(self):
        meta = FakeMetaAdapter()
        service, agent, _ = self.service([output()], meta=meta)
        first = service.process_payload(meta_payload())
        second = service.process_payload(meta_payload())
        self.assertEqual((first.status, second.status), ("sent", "duplicate"))
        self.assertEqual(agent.calls, 1)

    def test_07_bot_ownership_allows_v4(self):
        service, agent, _ = self.service([output()])
        result = service.process_payload(meta_payload())
        self.assertEqual(result.status, "sent")
        self.assertEqual(agent.calls, 1)

    def test_08_agent_ownership_blocks_v4(self):
        chatwoot = RecordingChatwoot(allowed=False)
        service, _, _ = self.service([], chatwoot=chatwoot)
        result = service.process_payload(meta_payload())
        self.assertEqual(result.status, "suppressed")

    def test_09_agent_owner_zero_llm_calls(self):
        service, agent, _ = self.service([], chatwoot=RecordingChatwoot(allowed=False))
        service.process_payload(meta_payload())
        self.assertEqual(agent.calls, 0)

    def test_10_botstate_persists_after_meta_turn(self):
        service, _, _ = self.service([output(updates={"origin_district": "Surco"})])
        service.process_payload(meta_payload())
        self.assertEqual(BotConversationState.objects.get().state_data["origin_district"], "Surco")

    def test_11_crm_sync_invoked(self):
        service, _, _ = self.service([output(updates={"origin_district": "Surco"})])
        service.process_payload(meta_payload())
        self.assertEqual(SolicitudCotizacion.objects.count(), 1)
        self.assertEqual(Cotizacion.objects.count(), 0)

    def test_12_customer_message_projected(self):
        service, _, chatwoot = self.service([output()])
        service.process_payload(meta_payload())
        self.assertEqual(len(chatwoot.customer_messages), 1)

    def test_13_bot_response_projected(self):
        service, _, chatwoot = self.service([output()])
        service.process_payload(meta_payload())
        self.assertEqual(len(chatwoot.bot_messages), 1)

    def test_14_meta_text_outbound_payload_correct(self):
        session = Mock()
        session.post.return_value = http_response(payload={"messages": [{"id": "wamid.out"}]})
        adapter = MetaV4Adapter(session=session, access_token="secret", api_version="v99.0")
        adapter.send_text(self.channel, OutboundMessage("51911112222", "Respuesta", 1))
        kwargs = session.post.call_args.kwargs
        self.assertEqual(kwargs["json"], {"messaging_product": "whatsapp", "to": "51911112222", "type": "text", "text": {"body": "Respuesta"}})
        self.assertEqual(kwargs["timeout"], 8)

    def test_15_meta_success_stores_outbound_wamid(self):
        service, _, _ = self.service([output()])
        result = service.process_payload(meta_payload())
        outgoing = MensajeWhatsApp.objects.get(pk=result.outbound_message_id)
        self.assertEqual(outgoing.meta_message_id, "wamid.out.1")
        self.assertEqual(outgoing.estado, "enviado")

    def test_16_meta_http_error_handled_safely(self):
        session = Mock()
        session.post.return_value = http_response(ok=False, status=400, payload={"error": {"code": 131000, "message": "Safe Meta error"}})
        result = MetaV4Adapter(session=session, access_token="secret").send_text(
            self.channel, OutboundMessage("51911112222", "Respuesta", 1)
        )
        self.assertFalse(result.sent)
        self.assertEqual((result.status_code, result.error_code), (400, "131000"))
        self.assertNotIn("secret", result.error_message)

    def test_17_repeated_webhook_has_no_duplicate_reply(self):
        meta = FakeMetaAdapter()
        service, _, _ = self.service([output()], meta=meta)
        service.process_payload(meta_payload())
        service.process_payload(meta_payload())
        self.assertEqual(len(meta.sent), 1)
        self.assertEqual(MensajeWhatsApp.objects.filter(direccion="saliente").count(), 1)

    def test_18_complete_state_handoff_ready_for_quote(self):
        updates = {"origin_district": "Surco", "destination_district": "Miraflores", "origin_floor": 1, "destination_floor": 2, "destination_access": "escaleras", "items": ["1 cama"]}
        service, _, _ = self.service([output(updates=updates, reply="Datos listos para cotizar.")])
        result = service.process_payload(meta_payload())
        self.assertTrue(result.ready_to_quote)
        self.assertEqual(SolicitudCotizacion.objects.get().datos_faltantes, [])

    def test_19_incomplete_state_stays_conversational(self):
        service, _, _ = self.service([output(updates={"origin_district": "Surco"})])
        result = service.process_payload(meta_payload())
        self.assertFalse(result.ready_to_quote)
        self.assertTrue(SolicitudCotizacion.objects.get().datos_faltantes)

    def test_20_chatwoot_failure_does_not_corrupt_state(self):
        service, _, _ = self.service([output(updates={"origin_district": "Surco"})], chatwoot=RecordingChatwoot(fail_projection=True))
        result = service.process_payload(meta_payload())
        self.assertEqual(result.status, "sent")
        self.assertEqual(BotConversationState.objects.get().state_data["origin_district"], "Surco")

    @override_settings(WHATSAPP_VERIFY_TOKEN="verify-v4")
    def test_entrypoint_verification_and_post(self):
        verify = self.client.get(reverse("meta-webhook-v4"), {"hub.mode": "subscribe", "hub.verify_token": "verify-v4", "hub.challenge": "123"})
        self.assertEqual((verify.status_code, verify.content), (200, b"123"))
        fake_service = Mock()
        fake_service.process_payload.return_value = Mock(status="ignored")
        with patch("apps.whatsapp_bot_v4.views.build_meta_webhook_service", return_value=fake_service):
            response = self.client.post(reverse("meta-webhook-v4"), data=meta_payload(), content_type="application/json")
        self.assertEqual(response.json(), {"status": "ignored"})
