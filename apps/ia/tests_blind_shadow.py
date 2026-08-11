from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from .blind_holdout import blind_holdout_cases
from .delta_contract_v2 import ConversationDeltaV2, empty_delta_v2
from .evidence_artifacts import read_evidence_run, run_evidence_cases
from .management.commands.compare_blind_shadow import _instrumented_result
from .providers import AIResult
from .delta_validator_v2 import validate_delta_v2 as real_validate_delta_v2


class BlindShadowHoldoutTests(SimpleTestCase):
    def test_holdout_size_sources_and_multiturn(self):
        cases = blind_holdout_cases()
        self.assertEqual(len(cases), 100)
        self.assertEqual(len({case["id"] for case in cases}), 100)
        self.assertEqual(sum(case["source"].startswith("historical") for case in cases), 40)
        self.assertGreaterEqual(sum(case["multiturn"] for case in cases), 20)

    def test_expected_labels_never_reach_model_or_validator_context(self):
        captured = {}

        def fake_extract(context, **kwargs):
            captured.update(context.payload)
            return empty_delta_v2(), AIResult(
                text=empty_delta_v2().model_dump_json(), provider="fake", model="fake",
                latency_ms=1, input_tokens=1, output_tokens=1,
            )

        case = blind_holdout_cases()[0]
        with patch(
            "apps.ia.management.commands.compare_blind_shadow.extract_conversation_delta",
            side_effect=fake_extract,
        ):
            _instrumented_result(case, 1)
        self.assertNotIn("expected", captured)
        self.assertNotIn("forbidden", captured)
        self.assertNotIn("id", captured)
        self.assertNotIn("source", captured)

    def test_validate_only_makes_no_provider_call(self):
        output = StringIO()
        with patch(
            "apps.ia.management.commands.compare_blind_shadow.extract_conversation_delta"
        ) as extract:
            call_command("compare_blind_shadow", validate_only=True, stdout=output)
        extract.assert_not_called()
        self.assertIn("100", output.getvalue())

    def test_fake_artifact_round_trip_preserves_detailed_evidence(self):
        model_payloads = []
        fake_delta = ConversationDeltaV2.model_validate({
            "schema_version": 2, "intent": "provide_information",
            "changes": {"lead": {"service": {
                "value": "carga", "evidence": "Hola", "evidence_type": "inferred",
            }}, "locations": []}, "corrections": [], "ambiguities": [],
        })

        def fake_extract(context, **kwargs):
            model_payloads.append(context.payload)
            return fake_delta, AIResult(
                text=fake_delta.model_dump_json(), provider="openai",
                model="gpt-4.1-mini", latency_ms=2, input_tokens=10, output_tokens=5,
            )

        with TemporaryDirectory() as directory:
            with patch(
                "apps.ia.evidence_artifacts.extract_conversation_delta",
                side_effect=fake_extract,
            ), patch(
                "apps.ia.evidence_artifacts.validate_delta_v2",
                wraps=real_validate_delta_v2,
            ) as validator:
                run_dir, _ = run_evidence_cases(
                    blind_holdout_cases()[:3], directory, run_suffix="fake")
                manifest, summary, records = read_evidence_run(run_dir)

        self.assertEqual(summary["records_written"], 3)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["raw_model_delta"]["schema_version"], 2)
        self.assertEqual(records[0]["raw_proposals"]["service"]["evidence"], "Hola")
        self.assertEqual(records[0]["validator"]["accepted_delta"]["schema_version"], 2)
        self.assertEqual(
            records[0]["validator"]["rejected_changes"][0]["reason_code"],
            "INFERRED_NOT_ALLOWED",
        )
        self.assertTrue(records[0]["evaluation"]["raw_false_positives"])
        self.assertTrue(records[1]["evaluation"]["raw_false_negatives"])
        self.assertIn("expected_delta_or_state", records[0]["evaluation"])
        self.assertEqual(manifest["case_count"], 3)
        self.assertTrue(all("expected" not in payload for payload in model_payloads))
        self.assertTrue(all(
            "expected" not in call.kwargs and "forbidden" not in call.kwargs
            for call in validator.call_args_list
        ))
