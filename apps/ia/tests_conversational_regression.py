"""
Regression tests for conversational policy fixes.
Tests for MISSING vs INVALID distinction and proper question flow.
"""
import unittest
from django.test import TestCase
from .conversation_engine import _rephrase_if_unanswered, _grouped_question, _next_missing_field
from apps.leads.models import Lead
from django.test.utils import override_settings


class RephraseLogicTest(TestCase):
    """Test the _rephrase_if_unanswered logic for MISSING vs INVALID."""

    def test_rephrase_should_only_trigger_on_retry(self):
        """
        BUG: _rephrase_if_unanswered uses REPHRASED_QUESTIONS even on FIRST attempt.

        Current (WRONG):
        - First time asking "datos_ruta": returns "Disculpa, no identifiqué bien los distritos"

        CORRECT:
        - First time asking "datos_ruta": should return None (no rephrase)
        - Second+ time asking "datos_ruta": should return rephrase
        """
        # Simulate: Lead has no districts, message is client's first response
        extracted = {}  # Client hasn't extracted distritos
        message = "Hola, necesito una mudanza"  # Cliente no menciona distritos

        # Crear lead sin distritos
        from apps.clientes.models import Cliente
        cliente = Cliente.objects.create(nombre="Test", telefono="+51999999999")
        lead = Lead.objects.create(cliente=cliente, tipo_servicio="mudanza")

        # Primera vez: expected_field = "datos_ruta", extracted = {}
        # El contador debería ser 0 (no ha sido preguntado antes)
        result = _rephrase_if_unanswered("datos_ruta", extracted, message, lead)

        # FAILING: Result es "Disculpa, no identifiqué..."
        # PASSING: Result debería ser None (no hay rephrase en primer intento)
        self.assertIsNone(result,
                         msg="First attempt should NOT trigger rephrase")


class MissingVsInvalidLogicTest(TestCase):
    """Test the semantic distinction between MISSING and INVALID."""

    def test_grouped_question_for_missing_districts(self):
        """
        When lead has NO districts at all, _grouped_question should return
        a SIMPLE QUESTION, not a rephrasing.
        """
        from apps.clientes.models import Cliente
        cliente = Cliente.objects.create(nombre="Test", telefono="+51999999999")
        lead = Lead.objects.create(cliente=cliente, tipo_servicio="mudanza")

        # Simulate decision with missing distritos
        from apps.ia.conversation_policy import decide_conversation
        decision = decide_conversation(lead)
        message = "Hola, necesito una mudanza"

        # This should call _grouped_question
        from .conversation_engine import _grouped_question
        response = _grouped_question(decision, message=message)

        # Should be simple question, not rephrase
        self.assertNotIn("no identif", response.lower(),
                        msg="Missing data should ask simply, not rephrase")

    def test_second_attempt_can_trigger_rephrase(self):
        """
        After asking and client fails to provide data twice, THEN rephrase is OK.
        """
        from apps.clientes.models import Cliente
        cliente = Cliente.objects.create(nombre="Test", telefono="+51999999999")
        lead = Lead.objects.create(cliente=cliente, tipo_servicio="mudanza")

        # Simulate: second attempt
        from .conversation_engine import _rephrase_counters
        _rephrase_counters[(lead.id, "datos_ruta")] = 1  # Second attempt

        extracted = {}  # Still no distritos
        message = "No lo sé"

        result = _rephrase_if_unanswered("datos_ruta", extracted, message, lead)

        # On RETRY, should have rephrase
        self.assertIsNotNone(result,
                           msg="Second attempt should trigger rephrase")
        self.assertIn("no identif", result.lower(),
                    msg="Rephrase should say 'no identifiqué'")
