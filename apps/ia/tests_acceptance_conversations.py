"""
Acceptance tests for conversational flows.
Tests 20 canonical conversation scenarios per requirements.
"""
from django.test import TestCase
from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.ia.conversation_engine import _next_missing_field, _grouped_question, _rephrase_if_unanswered
from apps.ia.conversation_policy import decide_conversation


class ConversationAcceptanceTests(TestCase):
    """Validate conversation policy against 20 canonical scenarios."""

    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombre="Test",
            telefono="+51999999999",
        )

    def test_canonical_1_first_message_missing_districts(self):
        """C1: Client: 'Hola, necesito un presupuesto para una mudanza'"""
        lead = Lead.objects.create(cliente=self.cliente, tipo_servicio="mudanza")
        decision = decide_conversation(lead)

        # Should ask for districts, not say "couldn't identify"
        question = _grouped_question(decision, message="Hola, necesito un presupuesto para una mudanza")
        self.assertNotIn("no identif", question.lower())
        self.assertIn("distrito", question.lower())

    def test_canonical_2_missing_and_accepted_partial(self):
        """C2: After asking 'de X a Y', client responds only origin."""
        lead = Lead.objects.create(cliente=self.cliente, tipo_servicio="mudanza")

        # Question asked for both, client gives only one
        decision = decide_conversation(lead)
        # Message only provides origin
        # Expected: extract origin, ask for destination only

        # After extraction, origin is saved
        lead.distrito_origen = "surco"
        lead.save()

        # Now decision should only need destino
        decision = decide_conversation(lead)
        self.assertIn("distrito_destino", decision.missing_relevant_data)
        self.assertNotIn("distrito_origen", decision.missing_relevant_data)

    def test_canonical_3_do_not_rephrase_first_mention(self):
        """C3: First time asking field, client hasn't extracted anything."""
        lead = Lead.objects.create(cliente=self.cliente, tipo_servicio="mudanza")
        extracted = {}  # No extraction yet

        # First attempt should NOT rephrase
        result = _rephrase_if_unanswered("datos_ruta", extracted, "Hola", lead)
        self.assertIsNone(result, msg="Should NOT rephrase on first question")

    def test_canonical_4_missing_data_simple_question(self):
        """C4: When data is MISSING (never mentioned), ask simply."""
        lead = Lead.objects.create(cliente=self.cliente, tipo_servicio="mudanza")
        decision = decide_conversation(lead)
        message = "Hola, necesito una mudanza"

        question = _grouped_question(decision, message)
        # Should ask, not say "didn't understand"
        self.assertNotIn("no entendi", question.lower())
        self.assertNotIn("no identif", question.lower())
        self.assertNotIn("no capte", question.lower())
