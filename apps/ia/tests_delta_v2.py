from django.test import SimpleTestCase

from .delta_contract_v2 import ConversationDeltaV2
from .delta_snapshot import CanonicalSnapshot
from .delta_validator_v2 import (
    AMBIGUOUS_REF,
    INFERRED_NOT_ALLOWED,
    NO_EVIDENCE,
    NO_OP,
    UNSUPPORTED_NORMALIZATION,
    validate_delta_v2,
)


class EvidenceBoundDeltaValidatorTests(SimpleTestCase):
    def setUp(self):
        self.snapshot = CanonicalSnapshot(
            state_version="v1",
            state={
                "service": "mudanza",
                "locations": {
                    "origin": {"district": "Surco", "floor": 3, "elevator": None,
                               "truck_access": None, "carry_distance_m": None,
                               "access_observation": None},
                    "destination": {"district": "Miraflores", "floor": 2,
                                    "elevator": False, "truck_access": None,
                                    "carry_distance_m": None, "access_observation": None},
                },
                "load": "cama",
                "staff": {"required": True},
                "additional_services": {"packing": "sin embalaje",
                                        "disassembly_required": False,
                                        "assembly_required": False},
            },
        )

    def _delta(self, locations=None, lead=None, ambiguities=None):
        return ConversationDeltaV2.model_validate({
            "schema_version": 2,
            "intent": "provide_information",
            "changes": {"lead": lead or {}, "locations": locations or []},
            "corrections": [],
            "ambiguities": ambiguities or [],
        })

    def test_accepts_explicit_contextual_value(self):
        delta = self._delta(locations=[{
            "ref": "origin", "ref_evidence": "en el origen",
            "ref_evidence_type": "explicit_contextual",
            "set": {"elevator": {"value": True, "evidence": "si en el origen",
                                   "evidence_type": "explicit_contextual"}},
        }])
        result = validate_delta_v2(delta, self.snapshot, customer_message="si en el origen")
        self.assertFalse(result.rejected)
        self.assertTrue(result.accepted.changes.locations[0].set.elevator.value)

    def test_rejects_inferred_operational_conclusion(self):
        delta = self._delta(locations=[{
            "ref": "destination", "ref_evidence": "destino",
            "ref_evidence_type": "explicit",
            "set": {"truck_access": {"value": False, "evidence": "queda lejos en destino",
                                       "evidence_type": "inferred"}},
        }])
        result = validate_delta_v2(delta, self.snapshot, customer_message="queda lejos en destino")
        self.assertIn(INFERRED_NOT_ALLOWED, [item.reason for item in result.rejected])
        self.assertFalse(result.accepted.changes.locations)

    def test_rejects_snapshot_only_evidence(self):
        delta = self._delta(lead={"service": {
            "value": "mudanza", "evidence": "mudanza", "evidence_type": "explicit"
        }})
        result = validate_delta_v2(delta, self.snapshot, customer_message="también una mesa")
        self.assertEqual(result.rejected[0].reason, NO_EVIDENCE)

    def test_prunes_no_op(self):
        delta = self._delta(lead={"service": {
            "value": "mudanza", "evidence": "mudanza", "evidence_type": "explicit"
        }})
        result = validate_delta_v2(delta, self.snapshot, customer_message="mudanza")
        self.assertEqual(result.rejected[0].reason, NO_OP)
        self.assertIsNone(result.accepted.changes.lead.service)

    def test_rejects_invented_numeric_normalization(self):
        delta = self._delta(locations=[{
            "ref": "destination", "ref_evidence": "destino",
            "ref_evidence_type": "explicit",
            "set": {"carry_distance_m": {"value": 100, "evidence": "una cuadra en destino",
                                           "evidence_type": "explicit"}},
        }])
        result = validate_delta_v2(delta, self.snapshot, customer_message="una cuadra en destino")
        self.assertIn(UNSUPPORTED_NORMALIZATION, [item.reason for item in result.rejected])

    def test_rejects_endpoint_not_colocated_with_value_evidence(self):
        delta = self._delta(locations=[{
            "ref": "origin", "ref_evidence": "Surco tercer piso",
            "ref_evidence_type": "explicit",
            "set": {"elevator": {"value": False, "evidence": "Miraflores sin ascensor",
                                   "evidence_type": "explicit"}},
        }])
        result = validate_delta_v2(
            delta, self.snapshot,
            customer_message="Surco tercer piso y Miraflores sin ascensor",
        )
        self.assertIn(AMBIGUOUS_REF, [item.reason for item in result.rejected])

    def test_preserves_anchored_ambiguity(self):
        delta = self._delta(ambiguities=[{
            "field": "access_observation", "value": "se estaciona a una cuadra",
            "possible_refs": ["origin", "destination"],
            "evidence": "se estaciona a una cuadra",
        }])
        result = validate_delta_v2(
            delta, self.snapshot, customer_message="el camión se estaciona a una cuadra"
        )
        self.assertEqual(result.accepted.ambiguities[0].field, "access_observation")

    def test_converts_unbound_observation_to_structured_ambiguity(self):
        delta = self._delta(locations=[{
            "ref": "destination", "ref_evidence": "Miraflores segundo piso",
            "ref_evidence_type": "explicit",
            "set": {"access_observation": {
                "value": "el camión queda lejos",
                "evidence": "el camión queda lejos",
                "evidence_type": "explicit",
            }},
        }])
        result = validate_delta_v2(
            delta, self.snapshot,
            customer_message="Miraflores segundo piso. el camión queda lejos",
        )
        self.assertFalse(result.accepted.changes.locations)
        self.assertEqual(result.accepted.ambiguities[0].field, "access_observation")
        self.assertEqual(
            result.accepted.ambiguities[0].possible_refs,
            ["destination", "origin"],
        )

    def test_rejects_both_without_evidence_for_both_endpoints(self):
        delta = self._delta(locations=[{
            "ref": "both", "ref_evidence": "se estaciona lejos",
            "ref_evidence_type": "explicit",
            "set": {"access_observation": {
                "value": "se estaciona lejos", "evidence": "se estaciona lejos",
                "evidence_type": "explicit",
            }},
        }])
        result = validate_delta_v2(
            delta, self.snapshot, customer_message="el camión se estaciona lejos"
        )
        self.assertIn(AMBIGUOUS_REF, [item.reason for item in result.rejected])
        self.assertEqual(result.accepted.ambiguities[0].field, "access_observation")

    def test_accepts_both_when_last_question_supplies_context(self):
        delta = self._delta(locations=[{
            "ref": "both", "ref_evidence": "en los dos",
            "ref_evidence_type": "explicit_contextual",
            "set": {"elevator": {
                "value": True, "evidence": "sí, en los dos",
                "evidence_type": "explicit_contextual",
            }},
        }])
        result = validate_delta_v2(
            delta,
            self.snapshot,
            customer_message="sí, en los dos",
            last_bot_question="¿Tienen ascensor en ambos lugares?",
        )
        self.assertFalse(result.rejected)
        self.assertEqual(result.accepted.changes.locations[0].ref, "both")
