from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from .blind_holdout import blind_holdout_cases
from .delta_contract_v2 import empty_delta_v2
from .management.commands.compare_blind_shadow import _instrumented_result
from .providers import AIResult


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
