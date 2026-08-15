from pathlib import Path

from django.test import TestCase

from apps.cotizador.models import SolicitudCotizacion
from apps.whatsapp.models import WhatsAppChannel

from ..adapters.crm import CRMV4Adapter
from ..domain.state import Access
from ..models import V4ChannelRoute
from ..repositories.state import DjangoBotStateRepository
from ..services.conversation_service import ConversationService
from ..services.meta_webhook_service import MetaWebhookV4Service
from ..services.persistent_conversation_service import PersistentConversationService
from .fakes import ScriptedAgent, output
from .meta_fakes import FakeMetaAdapter, RecordingChatwoot, meta_payload


class MetaFixtureIntegrationTests(TestCase):
    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            nombre="Channel TEST V4 integration", phone_number_id="meta-v4-test", activo=True
        )
        V4ChannelRoute.objects.create(channel=self.channel, enabled=True)

    def build(self, outputs, *, chatwoot=None):
        agent = ScriptedAgent(outputs)
        meta = FakeMetaAdapter()
        chatwoot = chatwoot or RecordingChatwoot()
        service = MetaWebhookV4Service(
            meta_adapter=meta,
            persistent_service=PersistentConversationService(
                ConversationService(agent), DjangoBotStateRepository(),
                crm_adapter=CRMV4Adapter(), chatwoot_adapter=chatwoot,
            ),
            chatwoot_adapter=chatwoot,
        )
        return service, agent, meta, chatwoot

    def test_complete_multi_turn_through_meta_fixtures(self):
        outputs = [
            output(reply="Hola, cuéntame de dónde a dónde sería."),
            output(updates={"origin_district": "San Isidro", "destination_district": "Miraflores"}),
            output(updates={"origin_floor": 1}),
            output(updates={"destination_floor": 2}),
            output(updates={"destination_access": "escaleras"}),
            output(updates={"items": ["1 cama"]}, reply="Datos listos para cotizar."),
        ]
        messages = ["Hola, necesito una mudanza", "de San Isidro a Miraflores", "primer piso", "segundo piso", "escaleras", "una cama"]
        service, agent, meta, chatwoot = self.build(outputs)
        result = None
        for index, message in enumerate(messages, 1):
            result = service.process_payload(meta_payload(message, wamid=f"wamid.multi.{index}"))
        state = DjangoBotStateRepository().load("whatsapp:1")
        self.assertTrue(result.ready_to_quote)
        self.assertEqual((state.origin_district, state.destination_district), ("San Isidro", "Miraflores"))
        self.assertEqual((state.origin_floor, state.origin_access), (1, Access.NOT_APPLICABLE))
        self.assertEqual((state.destination_floor, state.destination_access), (2, Access.STAIRS))
        self.assertEqual(state.items, ["1 cama"])
        self.assertEqual((agent.calls, len(meta.sent), len(chatwoot.customer_messages), len(chatwoot.bot_messages)), (6, 6, 6, 6))
        self.assertEqual(SolicitudCotizacion.objects.get().datos_faltantes, [])

    def test_all_data_one_turn_through_meta_fixture(self):
        updates = {"origin_district": "San Isidro", "destination_district": "Miraflores", "origin_floor": 1, "destination_floor": 2, "destination_access": "escaleras", "items": ["1 cama"]}
        service, agent, meta, _ = self.build([output(updates=updates, reply="Datos listos para cotizar.")])
        result = service.process_payload(meta_payload("Necesito mudar una cama de San Isidro a Miraflores. Salgo de primer piso y llego a segundo por escaleras."))
        self.assertTrue(result.ready_to_quote)
        self.assertEqual(agent.calls, 1)
        self.assertNotIn("?", meta.sent[0][1].text)

    def test_takeover_blocks_then_bot_resumes_persisted_route(self):
        chatwoot = RecordingChatwoot()
        service, agent, meta, _ = self.build([
            output(updates={"origin_district": "San Isidro", "destination_district": "Miraflores"}),
            output(updates={"origin_floor": 1}),
        ], chatwoot=chatwoot)
        service.process_payload(meta_payload("de San Isidro a Miraflores", wamid="wamid.take.1"))
        chatwoot.allowed = False
        blocked = service.process_payload(meta_payload("salgo del primer piso", wamid="wamid.take.2"))
        self.assertEqual((blocked.status, blocked.llm_calls, len(meta.sent)), ("suppressed", 0, 1))
        chatwoot.allowed = True
        resumed = service.process_payload(meta_payload("salgo del primer piso", wamid="wamid.take.3"))
        state = DjangoBotStateRepository().load("whatsapp:1")
        self.assertEqual(resumed.status, "sent")
        self.assertEqual((state.origin_district, state.destination_district, state.origin_floor), ("San Isidro", "Miraflores", 1))
        self.assertEqual(agent.calls, 2)


    def test_boundary_semantics_exact_timestamp(self):
        # Verificar que boundary filtra correctamente: fecha_mensaje__gt boundary
        # - Mensaje con timestamp < boundary → EXCLUIDO
        # - Mensaje con timestamp == boundary → EXCLUIDO (> no >=)
        # - Mensaje con timestamp > boundary → INCLUIDO
        from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
        from apps.clientes.models import Cliente
        from apps.leads.models import Lead
        from django.utils import timezone
        from datetime import timedelta

        client = Cliente.objects.create(telefono="51999999989")
        lead = Lead.objects.create(cliente=client)
        conversation = ConversacionWhatsApp.objects.create(cliente=client, lead=lead, channel=self.channel)

        base_time = timezone.now()

        # Mensaje antes de boundary
        MensajeWhatsApp.objects.create(
            conversacion=conversation,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            tipo="texto",
            contenido="dato viejo",
            estado="entregado",
            fecha_mensaje=base_time - timedelta(minutes=5),
        )

        # Boundary en este momento
        boundary_time = base_time

        # Mensaje en el exact boundary
        MensajeWhatsApp.objects.create(
            conversacion=conversation,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            tipo="texto",
            contenido="exacto en boundary",
            estado="entregado",
            fecha_mensaje=boundary_time,
        )

        # Mensaje después de boundary
        MensajeWhatsApp.objects.create(
            conversacion=conversation,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            tipo="texto",
            contenido="nuevo dato",
            estado="entregado",
            fecha_mensaje=base_time + timedelta(minutes=1),
        )

        # Verificar filtrado: query.filter(fecha_mensaje__gt=request_boundary_at)
        from ..services.meta_webhook_service import MetaWebhookV4Service
        history, _ = MetaWebhookV4Service._recent_context(
            conversation,
            exclude_message_id=-1,
            request_boundary_at=boundary_time,
        )

        # Solo msg_after debe estar incluido
        contents = [h["content"] for h in history]
        self.assertNotIn("dato viejo", contents)
        self.assertNotIn("exacto en boundary", contents)  # == boundary excluido
        self.assertIn("nuevo dato", contents)

    def test_request_boundary_filters_old_conversation_history(self):
        # Test: conversación con 10 mensajes previos mencionando Surco/Miraflores
        # request_boundary_at está seteado después de esos mensajes
        # nuevo cliente envía "hola quiero cotizar una mudanza"
        # → bot NO debe mencionar Surco/Miraflores (historial está cortado)
        from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
        from apps.clientes.models import Cliente
        from apps.leads.models import Lead
        from django.utils import timezone
        from datetime import timedelta

        # Crear cliente y conversación con historial
        client = Cliente.objects.create(telefono="51999999999")
        lead = Lead.objects.create(cliente=client)
        conversation = ConversacionWhatsApp.objects.create(
            cliente=client, lead=lead, channel=self.channel
        )

        # Crear 10 mensajes previos con Surco/Miraflores
        old_time = timezone.now() - timedelta(hours=2)
        old_messages = [
            ("Cliente", "de surco a miraflores"), ("Bot", "¿A qué piso llegas?"),
            ("Cliente", "piso 2"), ("Bot", "¿Acceso?"),
            ("Cliente", "escaleras"), ("Bot", "¿Qué muebles?"),
            ("Cliente", "una cama"), ("Bot", "Datos listos"),
            ("Cliente", "ok"), ("Bot", "Cotización hecha"),
        ]
        for i, (origen, contenido) in enumerate(old_messages):
            origen_enum = MensajeWhatsApp.ORIGEN_CLIENTE if origen == "Cliente" else MensajeWhatsApp.ORIGEN_BOT
            MensajeWhatsApp.objects.create(
                conversacion=conversation,
                origen=origen_enum,
                tipo="texto",
                contenido=contenido,
                estado="entregado",
                fecha_mensaje=old_time + timedelta(minutes=i),
            )

        # Cargar estado (crea BotConversationState con request_boundary_at si hay historial)
        repo = DjangoBotStateRepository()
        state = repo.load(f"whatsapp:{conversation.pk}")
        self.assertIsNotNone(state)  # Estado debe estar creado

        # Verificar que request_boundary_at fue seteado (historial aislado)
        from ..models import BotConversationState
        bot_state_model = BotConversationState.objects.get(conversation_key=f"whatsapp:{conversation.pk}")
        self.assertIsNotNone(bot_state_model.request_boundary_at)

        # Nuevo cliente envía "hola quiero cotizar una mudanza"
        # El bot debe responder sin mencionar Surco ni Miraflores
        service, agent, meta, _ = self.build([
            output(reply="Claro, para comenzar, de qué distrito a qué distrito será?")
        ])

        result = service.process_payload(meta_payload(
            "hola quiero cotizar una mudanza",
            customer="51988887777",
            wamid="wamid.boundary.1",
        ))

        # Verificaciones:
        # 1. Bot respondió
        self.assertEqual(result.status, "sent")
        # 2. Respuesta no contiene Surco ni Miraflores
        bot_reply = meta.sent[0][1].text
        self.assertNotIn("Surco", bot_reply)
        self.assertNotIn("Miraflores", bot_reply)
        self.assertNotIn("surco", bot_reply)
        self.assertNotIn("miraflores", bot_reply)
        # 3. Agent fue llamado solo 1 vez (sin reparación)
        self.assertEqual(agent.calls, 1)


class LegacyDependencyAuditTests(TestCase):
    FORBIDDEN = (
        "conversation_engine", "extract_lead_with_ai", "classify_request_intent",
        "request_lifecycle", "simple_response_renderer", "apps.ia",
    )

    def test_zero_legacy_conversational_imports(self):
        root = Path(__file__).resolve().parents[1]
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in root.rglob("*.py")
            if "tests" not in path.parts and "migrations" not in path.parts
        )
        for forbidden in self.FORBIDDEN:
            self.assertNotIn(forbidden, source)
