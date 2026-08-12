import json
from unittest.mock import Mock,patch

from django.test import TestCase

from apps.clientes.models import Cliente
from apps.integrations.models import BotGeneration
from apps.leads.models import Lead,LeadUbicacion
from apps.whatsapp.models import ConversacionWhatsApp,WhatsAppChannel

from .conversation_orchestrator import AskedTarget,orchestrate_conversation,validate_asked_targets
from .conversation_policy import decide_conversation,quote_requirements
from .providers import AIResult


class ConversationOrchestratorTests(TestCase):
    def setUp(self):
        client=Cliente.objects.create(telefono="51900000666")
        channel=WhatsAppChannel.objects.create(nombre="TEST orchestrator",phone_number_id="orch")
        self.lead=Lead.objects.create(cliente=client,whatsapp_channel=channel,
            tipo_servicio="mudanza",lista_objetos="cama y cajas")
        LeadUbicacion.objects.create(lead=self.lead,orden=0,tipo="origen",distrito="Surco")
        LeadUbicacion.objects.create(lead=self.lead,orden=1,tipo="destino",distrito="Miraflores")
        conversation=ConversacionWhatsApp.objects.create(cliente=client,lead=self.lead,channel=channel)
        self.generation=BotGeneration.objects.create(conversation=conversation,
            control_version_started=0,request_key="orchestrator-test")

    @patch("apps.ia.conversation_orchestrator.build_provider")
    def test_gpt_selects_subset_and_targets_are_persisted(self,build_provider):
        response={"reply_text":"¿En qué pisos están ambos lugares?",
            "asked_targets":[{"field":"floor","ref":"origin"},{"field":"floor","ref":"destination"}],
            "conversation_intent":"ASK"}
        fake=Mock();fake.generate_structured.return_value=AIResult(json.dumps(response),"fake","fake",1)
        build_provider.return_value=fake
        reply,targets=orchestrate_conversation(lead=self.lead,
            decision=decide_conversation(self.lead),customer_message="Quiero una mudanza",
            recent_turns=[],generation_id=self.generation.id)
        self.assertIn("pisos",reply)
        self.assertEqual([item["field"] for item in targets],["floor","floor"])
        self.generation.refresh_from_db()
        self.assertEqual(self.generation.asked_targets,targets)

    def test_commercial_target_rejects_entire_response(self):
        state={"locations":{"origin":{},"destination":{}}}
        with self.assertRaises(ValueError):
            validate_asked_targets([AskedTarget(field="price")],state)
        with self.assertRaises(ValueError):
            validate_asked_targets([AskedTarget(field="floor",ref="unknown")],state)

    def test_requirements_separate_quote_optional_and_booking_only(self):
        requirements=quote_requirements(self.lead)
        self.assertEqual(requirements.optional,("dni",))
        self.assertIn("fecha_servicio",requirements.booking_only)
        self.assertNotIn("fecha_servicio",requirements.required)

    @patch("apps.ia.conversation_orchestrator.build_provider")
    def test_payload_has_state_missing_and_no_expected_evidence(self,build_provider):
        response={"reply_text":"Cuéntame en qué pisos están.",
            "asked_targets":[{"field":"floor","ref":"origin"}],"conversation_intent":"ASK"}
        fake=Mock();fake.generate_structured.return_value=AIResult(json.dumps(response),"fake","fake",1)
        build_provider.return_value=fake
        orchestrate_conversation(lead=self.lead,decision=decide_conversation(self.lead),
            customer_message="hola",recent_turns=[{"author":"bot","text":"Hola"}],
            generation_id=self.generation.id)
        payload=json.loads(fake.generate_structured.call_args.args[0][1]["content"])
        self.assertIn("canonical_state",payload)
        self.assertIn("missing_required",payload)
        self.assertNotIn("expected",payload)
        self.assertIsNone(payload["commercial_state"]["pricing_result"])

    def test_ten_free_form_conversation_outputs_keep_domain_contract(self):
        state={"locations":{"origin":{},"destination":{}}}
        scenarios=[
            ("ASK",[("floor","origin")]),
            ("ASK",[("floor","destination")]),
            ("CLARIFY",[("elevator","destination")]),
            ("ASK",[("staff_required",None)]),
            ("ANSWER_AND_ASK",[("packing_required",None)]),
            ("ASK",[("truck_access","origin")]),
            ("ASK",[("truck_access","both")]),
            ("ASK",[("load",None)]),
            ("INFORM",[]),
            ("HANDOFF",[]),
        ]
        for intent,raw_targets in scenarios:
            with self.subTest(intent=intent,targets=raw_targets):
                targets=[AskedTarget(field=field,ref=ref) for field,ref in raw_targets]
                accepted=validate_asked_targets(targets,state)
                self.assertEqual(len(accepted),len(raw_targets))
                self.assertNotIn("price",{item["field"] for item in accepted})
