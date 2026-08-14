from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import TestCase

from apps.clientes.models import Cliente
from apps.cotizador.models import CotizacionComercial, RevisionCotizacion, SolicitudCotizacion
from apps.integrations.models import ConversationControl
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel

from ..adapters.chatwoot import ChatwootV4Adapter
from ..adapters.crm import CRMV4Adapter
from ..ai.schemas import ConversationAction
from ..domain.state import Access, BotState
from ..models import BotConversationState
from ..repositories.state import DjangoBotStateRepository
from ..services.conversation_service import ConversationService
from ..services.persistent_conversation_service import PersistentConversationService
from ..services.quote_bridge import AUTO_QUOTE, HUMAN_QUOTE, QuoteBridge, quote_input_hash
from .fakes import ScriptedAgent, output


class QuoteFlowTests(TestCase):
    def setUp(self):
        customer = Cliente.objects.create(telefono="51988000001")
        self.channel = WhatsAppChannel.objects.create(nombre="V4 quote", phone_number_id="quote-v4")
        self.lead = Lead.objects.create(cliente=customer, whatsapp_channel=self.channel)
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=customer, lead=self.lead, channel=self.channel,
        )
        ConversationControl.objects.create(conversation=self.conversation)
        self.repository = DjangoBotStateRepository()
        self.key = f"whatsapp:{self.conversation.pk}"
        self.complete = BotState(
            "Surco", "Miraflores", 1, 2,
            Access.NOT_APPLICABLE, Access.STAIRS, ["1 cama"],
        )

    @staticmethod
    def technical(price="450.00"):
        return SimpleNamespace(precio_min=Decimal("400.00"), precio_max=Decimal(price), precio_recomendado=Decimal("425.00"))

    def bridge(self, *, fail=False, price="450.00"):
        pricing = Mock(side_effect=RuntimeError("no_safe_price")) if fail else Mock(return_value=self.technical(price))

        def factory(conversation, technical, message, *, source_key):
            quote = CotizacionComercial.objects.create(
                codigo=f"V4-{CotizacionComercial.objects.count()+1}", lead=conversation.lead,
                channel=conversation.channel, origen="bot",
            )
            revision = RevisionCotizacion.objects.create(
                cotizacion=quote, source_key=source_key, numero=1,
                precio_final=technical.precio_max, mensaje_whatsapp=message,
            )
            return quote, revision, True

        return QuoteBridge(pricing_service=pricing, auto_quote_factory=factory), pricing

    def service(self, outputs, *, fail=False, chatwoot=None, price="450.00"):
        bridge, pricing = self.bridge(fail=fail, price=price)
        agent = ScriptedAgent(outputs)
        service = PersistentConversationService(
            ConversationService(agent), self.repository,
            crm_adapter=CRMV4Adapter(), chatwoot_adapter=chatwoot,
            quote_bridge=bridge,
        )
        return service, agent, pricing

    def process(self, service, message):
        return service.process_turn(
            conversation_key=self.key, customer_message=message,
            conversation=self.conversation, lead=self.lead,
        )

    def test_last_field_triggers_auto_quote_same_turn(self):
        state = self.complete.copy(); state.items = []
        self.repository.save(self.key, state)
        service, agent, pricing = self.service([output(updates={"items": ["1 cama"]}, reply="Datos listos")])
        result = self.process(service, "una cama")
        self.assertEqual(result.quote_decision.mode, AUTO_QUOTE)
        self.assertIn("S/ 450.00", result.turn.reply)
        self.assertEqual((agent.calls, pricing.call_count), (1, 1))
        self.assertEqual(BotConversationState.objects.get().status, BotConversationState.STATUS_QUOTED)

    def test_all_data_one_turn_quotes(self):
        updates = self.complete.to_dict()
        service, _, _ = self.service([output(updates=updates, reply="Datos listos")])
        result = self.process(service, "todo en un mensaje")
        self.assertEqual(result.quote_decision.mode, AUTO_QUOTE)

    def test_no_safe_price_creates_pending_human(self):
        service, _, _ = self.service([output(updates=self.complete.to_dict(), reply="Datos listos")], fail=True)
        result = self.process(service, "todo")
        self.assertEqual(result.quote_decision.mode, HUMAN_QUOTE)
        self.assertEqual(SolicitudCotizacion.objects.filter(estado="pendiente").count(), 1)
        self.assertEqual(BotConversationState.objects.get().status, BotConversationState.STATUS_PENDING_HUMAN)

    def test_ok_after_quoted_skips_agent_and_quote(self):
        service, agent, pricing = self.service([output(updates=self.complete.to_dict(), reply="listo")])
        self.process(service, "todo")
        result = self.process(service, "ok")
        self.assertEqual((result.turn.llm_calls, agent.calls, pricing.call_count), (0, 1, 1))
        self.assertEqual(RevisionCotizacion.objects.count(), 1)

    def test_repeated_final_message_does_not_create_request_or_quote(self):
        service, agent, pricing = self.service([
            output(updates=self.complete.to_dict(), reply="listo"),
            output(reply="Perfecto"),
        ])
        self.process(service, "todo")
        self.process(service, "una cama")
        self.assertEqual((SolicitudCotizacion.objects.count(), RevisionCotizacion.objects.count()), (1, 1))
        self.assertEqual((agent.calls, pricing.call_count), (2, 1))

    def test_gracias_after_quoted_skips_collection(self):
        service, agent, _ = self.service([output(updates=self.complete.to_dict(), reply="listo")])
        self.process(service, "todo")
        result = self.process(service, "gracias")
        self.assertEqual((result.turn.required_missing, agent.calls), ([], 1))

    def test_ok_pending_human_does_not_duplicate_request(self):
        service, agent, _ = self.service([output(updates=self.complete.to_dict(), reply="listo")], fail=True)
        self.process(service, "todo")
        self.process(service, "ok")
        self.assertEqual((SolicitudCotizacion.objects.count(), agent.calls), (1, 1))

    def test_correction_after_quote_requotes_new_revision(self):
        service, _, pricing = self.service([
            output(updates=self.complete.to_dict(), reply="listo"),
            output(corrections={"origin_district": "San Borja"}, reply="corregido"),
        ])
        self.process(service, "todo")
        result = self.process(service, "origen San Borja")
        self.assertEqual(result.turn.state.origin_district, "San Borja")
        self.assertEqual((pricing.call_count, RevisionCotizacion.objects.count()), (2, 2))

    def test_item_change_after_quote_requotes(self):
        service, _, pricing = self.service([
            output(updates=self.complete.to_dict(), reply="listo"),
            output(corrections={"items": ["1 cama", "20 cajas"]}, reply="agregado"),
        ])
        self.process(service, "todo")
        result = self.process(service, "también 20 cajas")
        self.assertEqual(result.turn.state.items, ["1 cama", "20 cajas"])
        self.assertEqual(pricing.call_count, 2)

    def test_same_state_bridge_is_idempotent(self):
        bridge, pricing = self.bridge()
        first = bridge.evaluate(state=self.complete, lead=self.lead, conversation=self.conversation)
        second = bridge.evaluate(state=self.complete, lead=self.lead, conversation=self.conversation)
        self.assertEqual(first.revision_id, second.revision_id)
        self.assertTrue(second.reused)
        self.assertEqual((pricing.call_count, RevisionCotizacion.objects.count()), (1, 1))

    def test_existing_pricing_and_commercial_services_are_reused(self):
        crm = CRMV4Adapter()
        crm_result = crm.sync(self.complete, self.lead)
        decision = QuoteBridge().evaluate(
            state=self.complete, lead=self.lead, conversation=self.conversation,
            request_id=crm_result.request_id,
        )
        self.assertEqual(decision.mode, AUTO_QUOTE)
        self.assertGreater(decision.price, 0)
        self.assertEqual((CotizacionComercial.objects.count(), RevisionCotizacion.objects.count()), (1, 1))

    def test_commercial_fingerprint_changes_only_with_quote_input(self):
        same = self.complete.copy()
        changed = self.complete.copy(); changed.destination_district = "San Borja"
        self.assertEqual(quote_input_hash(self.complete), quote_input_hash(same))
        self.assertNotEqual(quote_input_hash(self.complete), quote_input_hash(changed))

    def test_chatwoot_commercial_projection_runs(self):
        chatwoot = Mock()
        chatwoot.is_bot_allowed.return_value = True
        service, _, _ = self.service([output(updates=self.complete.to_dict(), reply="listo")], chatwoot=chatwoot)
        self.process(service, "todo")
        chatwoot.project_commercial_status.assert_called_once_with(self.conversation)

    def test_one_logical_block_validation(self):
        agent = ScriptedAgent([
            output(requested=["origin_district", "items"], reply="ruta y carga?"),
            output(requested=["origin_district", "destination_district"], reply="¿de dónde a dónde?"),
        ])
        result = ConversationService(agent).process_turn(state=BotState(), customer_message="hola")
        self.assertEqual(result.required_missing[0], "origin_district")
        self.assertEqual(agent.calls, 2)

    def test_canonical_local_conversation_quotes_on_last_turn(self):
        outputs = [
            output(requested=["origin_district", "destination_district"], reply="¿De qué distrito a qué distrito?"),
            output(updates={"origin_district": "Surco", "destination_district": "Cercado de Lima"}, requested=["origin_floor", "destination_floor"], reply="¿De qué piso salen y a cuál llegan?"),
            output(updates={"origin_floor": 1, "destination_floor": 2}, requested=["destination_access"], reply="¿Ascensor o escaleras en destino?"),
            output(updates={"destination_access": "escaleras"}, requested=["items"], reply="¿Qué cosas trasladarás?"),
            output(updates={"items": ["1 cama", "1 cocina", "1 escritorio"]}, reply="listo"),
        ]
        service, agent, pricing = self.service(outputs)
        result = None
        for message in ("Hola", "Surco a Cercado", "primer a segundo", "escaleras", "cama cocina escritorio"):
            result = self.process(service, message)
        self.assertEqual(result.quote_decision.mode, AUTO_QUOTE)
        self.assertEqual((agent.calls, pricing.call_count), (5, 1))

    def test_correction_from_transitory_ready_is_evaluated(self):
        self.repository.save(self.key, self.complete)
        self.assertEqual(BotConversationState.objects.get().status, BotConversationState.STATUS_READY)
        service, _, pricing = self.service([
            output(corrections={"origin_district": "San Borja"}, reply="corregido"),
        ])
        result = self.process(service, "origen San Borja")
        self.assertEqual(result.quote_decision.mode, AUTO_QUOTE)
        self.assertEqual(pricing.call_count, 1)

    def test_physical_regression_new_quote_after_quoted_starts_clean_request(self):
        first_lead_id = self.lead.pk
        service, agent, pricing = self.service([
            output(updates={
                "origin_district": "Surco",
                "destination_district": "Cercado de Lima",
                "origin_floor": 1,
                "destination_floor": 2,
                "origin_access": "NOT_APPLICABLE",
                "destination_access": "escaleras",
                "items": ["cama", "cocina", "escritorio"],
            }, reply="listo"),
            output(
                action="new_quote",
                requested=["origin_district", "destination_district"],
                reply="Claro, iniciemos una nueva cotización. ¿De qué distrito a qué distrito?",
            ),
        ], price="440.00")
        first = self.process(service, "datos completos")
        self.assertEqual(first.quote_decision.price, Decimal("440.00"))
        old_quote_id = RevisionCotizacion.objects.get(pk=first.quote_decision.revision_id).cotizacion_id

        result = self.process(service, "Hola, necesito un presupuesto para una mudanza")
        self.conversation.refresh_from_db()
        current = self.repository.load(self.key)
        archived = BotConversationState.objects.exclude(conversation_key=self.key).get()

        self.assertEqual(result.turn.conversation_action, ConversationAction.NEW_QUOTE)
        self.assertEqual(current, BotState())
        self.assertEqual(self.repository.get_commercial(self.key)["status"], BotConversationState.STATUS_COLLECTING)
        self.assertEqual(archived.status, BotConversationState.STATUS_QUOTED)
        self.assertEqual(archived.quote_price, Decimal("440.00"))
        self.assertNotEqual(self.conversation.lead_id, first_lead_id)
        self.assertTrue(CotizacionComercial.objects.filter(pk=old_quote_id, lead_id=first_lead_id).exists())
        self.assertEqual(Lead.objects.filter(cliente=self.conversation.cliente).count(), 2)
        self.assertEqual(SolicitudCotizacion.objects.filter(lead=self.conversation.lead).count(), 1)
        forbidden = ("440", "surco", "cercado", "cama", "cocina", "escritorio")
        self.assertFalse(any(value in result.turn.reply.lower() for value in forbidden))
        self.assertEqual((agent.calls, pricing.call_count), (2, 1))

    def test_explicit_new_quote_after_quoted_uses_same_customer_and_thread(self):
        service, _, _ = self.service([
            output(updates=self.complete.to_dict(), reply="listo"),
            output(action="new_quote", requested=["origin_district", "destination_district"], reply="¿Nueva ruta?"),
            output(
                updates={"origin_district": "Surco", "destination_district": "Miraflores"},
                requested=["origin_floor", "destination_floor"], reply="¿En qué pisos?",
            ),
        ])
        self.process(service, "todo")
        customer_id = self.conversation.cliente_id
        conversation_id = self.conversation.pk
        result = self.process(service, "quiero otra mudanza")
        route = self.process(service, "de surco a miraflores")
        self.conversation.refresh_from_db()
        self.assertEqual(result.turn.conversation_action, ConversationAction.NEW_QUOTE)
        self.assertEqual((self.conversation.pk, self.conversation.cliente_id), (conversation_id, customer_id))
        self.assertEqual((route.turn.state.origin_district, route.turn.state.destination_district), ("Surco", "Miraflores"))
        self.assertEqual(self.repository.load(self.key).destination_district, "Miraflores")

    def test_new_quote_after_pending_human_starts_clean_request(self):
        service, _, _ = self.service([
            output(updates=self.complete.to_dict(), reply="listo"),
            output(action="new_quote", requested=["origin_district", "destination_district"], reply="¿Nueva ruta?"),
        ], fail=True)
        self.process(service, "todo")
        old_lead_id = self.lead.pk
        result = self.process(service, "quiero cotizar otra mudanza")
        self.conversation.refresh_from_db()
        self.assertEqual(result.turn.conversation_action, ConversationAction.NEW_QUOTE)
        self.assertNotEqual(self.conversation.lead_id, old_lead_id)
        self.assertEqual(result.turn.state, BotState())

    def test_post_quote_actions_keep_current_request_except_new_quote(self):
        service, agent, pricing = self.service([
            output(updates=self.complete.to_dict(), reply="listo"),
            output(action="correction", corrections={"origin_district": "Miraflores"}, reply="corregido"),
            output(action="correction", corrections={"items": ["1 cama", "10 cajas"]}, reply="agregado"),
            output(action="question", reply="El detalle depende del servicio contratado.", question=True),
        ])
        self.process(service, "todo")
        lead_id = self.conversation.lead_id
        ok = self.process(service, "ok")
        thanks = self.process(service, "gracias")
        corrected = self.process(service, "el origen en realidad es Miraflores")
        items = self.process(service, "también son 10 cajas")
        question = self.process(service, "¿el precio incluye personal?")
        self.conversation.refresh_from_db()

        self.assertEqual((ok.turn.conversation_action, thanks.turn.conversation_action), (ConversationAction.ACK, ConversationAction.ACK))
        self.assertEqual(corrected.turn.conversation_action, ConversationAction.CORRECTION)
        self.assertEqual(items.turn.conversation_action, ConversationAction.CORRECTION)
        self.assertEqual(question.turn.conversation_action, ConversationAction.QUESTION)
        self.assertEqual(self.conversation.lead_id, lead_id)
        self.assertEqual(Lead.objects.filter(cliente=self.conversation.cliente).count(), 1)
        self.assertEqual(pricing.call_count, 3)
        self.assertEqual(agent.calls, 4)
