import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from .conversation_policy import QuestionTarget, _question_targets
from .delta_context import DeltaContext
from .delta_contract_v3 import ConversationDeltaV3
from .delta_extractor_v3 import extract_conversation_delta_v3
from .delta_snapshot import CanonicalSnapshot
from .delta_validator_v3 import (
    AMBIGUOUS_REF, ATTRIBUTE_CLOSURE, DERIVED_FIELD_FORBIDDEN,
    UNSUPPORTED_SPECIFICITY, validate_delta_v3,
)
from .providers import AIResult
from .v3_artifacts import run_v3_cases
from .v3_development import v3_development_cases


class DeltaValidatorV3Tests(SimpleTestCase):
    def setUp(self):
        self.snapshot = CanonicalSnapshot(state_version="v1", state={
            "service": "mudanza", "load": None, "staff": {"required": None},
            "additional_services": {"packing": None, "packing_required": None,
                                    "disassembly_required": None,
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
        return ConversationDeltaV3.model_validate({
            "schema_version": 3, "intent": "provide_information",
            "changes": {"lead": lead or {}, "locations": locations or []},
            "corrections": corrections or [], "ambiguities": [],
        })

    def validate(self, delta, message, targets=()):
        return validate_delta_v3(delta, self.snapshot, customer_message=message,
                                 question_targets=targets)

    def test_conversation_decision_builds_structured_targets(self):
        self.assertEqual(_question_targets(("ascensor_origen", "piso_destino")), (
            QuestionTarget("elevator", "origin"), QuestionTarget("floor", "destination")))

    def test_context_yes_resolves_origin_elevator(self):
        delta = self.delta(locations=[{"ref":"origin","ref_evidence":"sí",
            "ref_evidence_type":"inferred","set":{"elevator":{"value":True,
            "evidence":"sí","evidence_type":"inferred"}}}])
        result = self.validate(delta, "sí", [QuestionTarget("elevator", "origin")])
        self.assertTrue(result.accepted.changes.locations[0].set.elevator.value)

    def test_context_probable_yes_resolves_origin_elevator(self):
        delta = self.delta(locations=[{"ref":"origin","ref_evidence":"creo que sí",
            "ref_evidence_type":"inferred","set":{"elevator":{"value":True,
            "evidence":"creo que sí","evidence_type":"inferred"}}}])
        result = self.validate(delta, "creo que sí", [QuestionTarget("elevator", "origin")])
        self.assertTrue(result.accepted.changes.locations[0].set.elevator.value)

    def test_target_allows_independent_explicit_load(self):
        delta = self.delta(lead={"load":{"value":"20 cajas","evidence":"20 cajas",
            "evidence_type":"explicit"}}, locations=[{"ref":"origin","ref_evidence":"sí",
            "ref_evidence_type":"explicit_contextual","set":{"elevator":{"value":True,
            "evidence":"sí","evidence_type":"explicit_contextual"}}}])
        result = self.validate(delta, "sí, y son 20 cajas",
                               [QuestionTarget("elevator", "origin")])
        self.assertEqual(result.accepted.changes.lead.load.value, "20 cajas")

    def test_packing_required_keeps_mode_unknown(self):
        delta = self.delta(lead={"packing_required":{"value":True,"evidence":"sí",
            "evidence_type":"inferred"}})
        result = self.validate(delta, "sí", [QuestionTarget("packing_required")])
        self.assertTrue(result.accepted.changes.lead.packing_required.value)
        self.assertIsNone(result.accepted.changes.lead.packing_mode)

    def test_packing_required_rejects_invented_mode(self):
        delta = self.delta(lead={"packing_mode":{"value":"embalaje basico","evidence":"sí",
            "evidence_type":"explicit_contextual"}})
        result = self.validate(delta, "sí", [QuestionTarget("packing_required")])
        self.assertIn(UNSUPPORTED_SPECIFICITY, [item.reason for item in result.rejected])

    def test_staff_target_does_not_change_service(self):
        delta = self.delta(lead={
            "staff_required":{"value":True,"evidence":"con personal","evidence_type":"explicit"},
            "service":{"value":"carga","evidence":"con personal","evidence_type":"inferred"}})
        result = self.validate(delta, "con personal", [QuestionTarget("staff_required")])
        self.assertTrue(result.accepted.changes.lead.staff_required.value)
        self.assertIsNone(result.accepted.changes.lead.service)
        self.assertIn(ATTRIBUTE_CLOSURE, [item.reason for item in result.rejected])

    def test_pending_observation_resolves_destination(self):
        delta = self.delta(locations=[{"ref":"destination","ref_evidence":"en el destino",
            "ref_evidence_type":"explicit","set":{"access_observation":{
            "value":"queda lejos","evidence":"en el destino","evidence_type":"explicit_contextual"}}}])
        result = self.validate(delta, "en el destino",
                               [QuestionTarget("access_observation", "both")])
        self.assertEqual(result.accepted.changes.locations[0].ref, "destination")

    def test_access_without_target_becomes_ambiguity(self):
        delta = self.delta(locations=[{"ref":"origin","ref_evidence":"el camión queda lejos",
            "ref_evidence_type":"explicit","set":{"access_observation":{
            "value":"queda lejos","evidence":"el camión queda lejos","evidence_type":"explicit"}}}])
        result = self.validate(delta, "el camión queda lejos")
        self.assertIn(AMBIGUOUS_REF, [item.reason for item in result.rejected])
        self.assertEqual(result.accepted.ambiguities[0].field, "access_observation")

    def test_destination_correction_is_preserved(self):
        delta = self.delta(corrections=[{"target":"locations.destination.district",
            "old":"Miraflores","new":"San Isidro",
            "evidence":"no era Miraflores, era San Isidro","evidence_type":"explicit"}])
        result = self.validate(delta, "no era Miraflores, era San Isidro")
        self.assertEqual(result.accepted.corrections[0].new, "San Isidro")

    def test_derived_fields_are_forbidden(self):
        delta = self.delta(locations=[{"ref":"origin","ref_evidence":"origen 30 metros",
            "ref_evidence_type":"explicit","set":{"carry_distance_m":{"value":30,
            "evidence":"30 metros","evidence_type":"explicit"}}}])
        result = self.validate(delta, "origen 30 metros")
        self.assertIn(DERIVED_FIELD_FORBIDDEN, [item.reason for item in result.rejected])

    @patch("apps.ia.delta_extractor_v3.build_provider")
    def test_fake_provider_receives_target_and_v3_schema(self, build_provider):
        response = self.delta()
        fake = build_provider.return_value
        fake.generate_structured.return_value = AIResult(
            response.model_dump_json(), "fake", "fake-v3", 1, 10, 5)
        target = {"field":"elevator","ref":"origin","operation":"set"}
        context = DeltaContext(
            payload={"state":self.snapshot.state, "last_bot_question":"texto visible",
                     "last_question_targets":[target], "customer_message":"sí",
                     "recent_turns":[]}, last_bot_question="texto visible",
            recent_turn_count=0, question_targets=(target,))
        parsed, _ = extract_conversation_delta_v3(context, provider_name="openai")
        messages = fake.generate_structured.call_args.args[0]
        sent = json.loads(messages[1]["content"])
        self.assertEqual(sent["last_question_targets"], [target])
        self.assertIs(fake.generate_structured.call_args.kwargs["schema_model"], ConversationDeltaV3)
        self.assertEqual(parsed.schema_version, 3)

    def test_schema_forbids_commercial_authority(self):
        with self.assertRaises(Exception):
            ConversationDeltaV3.model_validate({
                "schema_version":3, "intent":"provide_information",
                "changes":{}, "pricing":100, "readiness":True})

    def test_development_targets_cover_all_contextual_cases(self):
        cases = v3_development_cases()
        contextual = [case for case in cases if case["last_bot_question"]]
        self.assertEqual(len(contextual), 45)
        self.assertTrue(all(case["question_targets"] for case in contextual))
        self.assertTrue(next(case for case in cases if case["id"] == "s02")
                        ["label_review_required"])

    @patch("apps.ia.v3_artifacts.extract_conversation_delta_v3")
    def test_harness_persists_complete_artifacts_with_fake_provider(self, extract):
        delta = self.delta()
        extract.return_value = (delta, AIResult(
            delta.model_dump_json(), "fake", "fake-v3", 2, 11, 4))
        cases = [case for case in v3_development_cases()
                 if case["id"] in {"s11", "s17", "s54"}]
        with tempfile.TemporaryDirectory() as directory:
            run_dir, summary = run_v3_cases(cases, Path(directory), run_suffix="fake")
            records = (run_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(records), 3)
            first = json.loads(records[0])
            self.assertIn("question_targets", first["input"])
            self.assertIn("raw_v3_delta", first)
            self.assertIn("accepted_v3_delta", first)
            self.assertIn("rejections", first)
            self.assertIn("accepted_false_negatives", first["evaluation"])
            self.assertEqual(summary["api_calls"], 3)
