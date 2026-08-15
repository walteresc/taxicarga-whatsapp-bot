from django.test import SimpleTestCase

from ..domain.merge import merge_state
from ..domain.requirements import ready_to_quote, required_missing
from ..domain.state import Access, BotState
from ..domain.validators import DomainValidationError


class DomainTests(SimpleTestCase):
    def test_initial_requirements(self):
        self.assertEqual(required_missing(BotState()), [
            "origin_district", "destination_district", "origin_floor", "destination_floor", "items"
        ])

    def test_floor_one_forces_not_applicable(self):
        state = merge_state(BotState(), {"origin_floor": 1}, {})
        self.assertEqual(state.origin_access, Access.NOT_APPLICABLE)

    def test_upper_floor_requires_access(self):
        state = merge_state(BotState(), {"origin_floor": 3}, {})
        self.assertIn("origin_access", required_missing(state))

    def test_null_update_does_not_erase(self):
        state = BotState(origin_district="Surco")
        self.assertEqual(merge_state(state, {"origin_district": None}, {}).origin_district, "Surco")

    def test_overwrite_requires_correction(self):
        # Comportamiento nuevo: conflictos en updates se permiten pero requieren confirmación
        # (se aplican con WARNING y pueden ser revocados en el siguiente turno si el cliente dice "no")
        # La distinción critical: updates (tentativa) vs corrections (definitiva)
        with self.assertLogs("apps.whatsapp_bot_v4.domain.merge", level="WARNING") as logs:
            state = merge_state(BotState(origin_district="Surco"), {"origin_district": "San Borja"}, {})
        # Conflicto debe estar loguado
        self.assertIn("bot_v4_merge_conflict_apply", logs.output[0])
        # El nuevo valor se aplica tentativo (no es definitivo como corrections)
        self.assertEqual(state.origin_district, "San Borja")

    def test_explicit_correction_overwrites(self):
        state = merge_state(BotState(origin_district="Surco"), {}, {"origin_district": "San Borja"})
        self.assertEqual(state.origin_district, "San Borja")

    def test_complete_state_is_ready(self):
        state = BotState("Surco", "Miraflores", 1, 2, Access.NOT_APPLICABLE, Access.STAIRS, ["1 cama"])
        self.assertTrue(ready_to_quote(state))
