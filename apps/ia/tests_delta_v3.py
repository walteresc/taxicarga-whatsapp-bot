from django.test import SimpleTestCase

from .conversation_policy import QuestionTarget, _question_targets
from .delta_contract_v2 import ConversationDeltaV2
from .delta_snapshot import CanonicalSnapshot
from .delta_validator_v3 import (
    AMBIGUOUS_REF, ATTRIBUTE_CLOSURE, DERIVED_FIELD_FORBIDDEN,
    UNSUPPORTED_SPECIFICITY, validate_delta_v3,
)


class DeltaValidatorV3Tests(SimpleTestCase):
    def setUp(self):
        self.snapshot = CanonicalSnapshot(state_version="v1", state={
            "service": "mudanza", "load": None, "staff": {"required": None},
            "additional_services": {"packing": None, "disassembly_required": None,
                                    "assembly_required": None},
            "locations": {
                "origin": {"district": "Surco", "floor": None, "elevator": None,
                           "truck_access": None, "carry_distance_m": None,
                           "access_observation": None},
                "destination": {"district": "Miraflores", "floor": None,
                                "elevator": None, "truck_access": None,
                                "carry_distance_m": None, "access_observation": None},
            },
        })

    def delta(self, *, lead=None, locations=None, corrections=None):
        return ConversationDeltaV2.model_validate({
            "schema_version": 2, "intent": "provide_information",
            "changes": {"lead": lead or {}, "locations": locations or []},
            "corrections": corrections or [], "ambiguities": [],
        })

    def test_conversation_decision_builds_structured_targets(self):
        targets = _question_targets(("ascensor_origen", "piso_destino"))
        self.assertEqual(targets, (
            QuestionTarget("elevator", "origin"),
            QuestionTarget("floor", "destination"),
        ))

    def test_context_target_normalizes_inferred_elevator(self):
        delta = self.delta(locations=[{"ref":"origin","ref_evidence":"sí",
            "ref_evidence_type":"inferred","set":{"elevator":{"value":True,
            "evidence":"sí","evidence_type":"inferred"}}}])
        result = validate_delta_v3(delta, self.snapshot, customer_message="sí",
            question_targets=[QuestionTarget("elevator", "origin")])
        self.assertTrue(result.accepted.changes.locations[0].set.elevator.value)

    def test_target_allows_independent_explicit_information(self):
        delta = self.delta(lead={"load":{"value":"20 cajas","evidence":"20 cajas",
            "evidence_type":"explicit"}}, locations=[{"ref":"origin","ref_evidence":"sí",
            "ref_evidence_type":"explicit_contextual","set":{"elevator":{"value":True,
            "evidence":"sí","evidence_type":"explicit_contextual"}}}])
        result = validate_delta_v3(delta, self.snapshot, customer_message="sí, 20 cajas",
            question_targets=[QuestionTarget("elevator", "origin")])
        self.assertEqual(result.accepted.changes.lead.load.value, "20 cajas")

    def test_packing_required_does_not_authorize_mode(self):
        delta = self.delta(lead={"packing":{"value":"embalaje basico","evidence":"sí",
            "evidence_type":"explicit_contextual"}})
        result = validate_delta_v3(delta, self.snapshot, customer_message="sí",
            question_targets=[QuestionTarget("packing_required")])
        self.assertIn(UNSUPPORTED_SPECIFICITY, [item.reason for item in result.rejected])

    def test_ambiguous_endpoint_becomes_ambiguity(self):
        delta = self.delta(locations=[{"ref":"origin","ref_evidence":"queda lejos",
            "ref_evidence_type":"explicit","set":{"access_observation":{"value":"queda lejos",
            "evidence":"queda lejos","evidence_type":"explicit"}}}])
        result = validate_delta_v3(delta, self.snapshot, customer_message="queda lejos")
        self.assertIn(AMBIGUOUS_REF, [item.reason for item in result.rejected])
        self.assertEqual(result.accepted.ambiguities[0].field, "access_observation")

    def test_access_target_fixes_endpoint(self):
        delta = self.delta(locations=[{"ref":"origin","ref_evidence":"queda lejos",
            "ref_evidence_type":"explicit_contextual","set":{"access_observation":{"value":"queda lejos",
            "evidence":"queda lejos","evidence_type":"explicit_contextual"}}}])
        result = validate_delta_v3(delta, self.snapshot, customer_message="queda lejos",
            question_targets=[QuestionTarget("access_observation", "origin")])
        self.assertEqual(result.accepted.changes.locations[0].ref, "origin")

    def test_contextual_service_cannot_escape_staff_target(self):
        delta = self.delta(lead={"service":{"value":"carga","evidence":"con personal",
            "evidence_type":"explicit_contextual"}})
        result = validate_delta_v3(delta, self.snapshot, customer_message="con personal",
            question_targets=[QuestionTarget("staff_required")])
        self.assertIn(ATTRIBUTE_CLOSURE, [item.reason for item in result.rejected])

    def test_correction_and_state_preservation(self):
        delta = self.delta(corrections=[{"target":"locations.destination.district",
            "old":"Miraflores","new":"San Isidro","evidence":"no era Miraflores, era San Isidro",
            "evidence_type":"explicit"}])
        result = validate_delta_v3(delta, self.snapshot,
            customer_message="no era Miraflores, era San Isidro")
        self.assertEqual(len(result.accepted.corrections), 1)
        self.assertFalse(result.accepted.changes.locations)

    def test_derived_fields_are_forbidden(self):
        delta = self.delta(locations=[{"ref":"origin","ref_evidence":"30 metros",
            "ref_evidence_type":"explicit","set":{"carry_distance_m":{"value":30,
            "evidence":"30 metros","evidence_type":"explicit"}}}])
        result = validate_delta_v3(delta, self.snapshot, customer_message="origen 30 metros")
        self.assertIn(DERIVED_FIELD_FORBIDDEN, [item.reason for item in result.rejected])
