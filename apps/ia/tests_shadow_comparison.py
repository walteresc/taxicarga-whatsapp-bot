from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.ia.management.commands.compare_delta_shadow import legacy_result, score


class DeltaShadowComparisonHarnessTests(SimpleTestCase):
    def test_validate_only_never_calls_openai(self):
        from unittest.mock import patch

        output = StringIO()
        with patch(
            "apps.ia.management.commands.compare_delta_shadow.extract_conversation_delta"
        ) as provider:
            call_command("compare_delta_shadow", "--validate-only", stdout=output)

        provider.assert_not_called()
        self.assertIn("40 casos", output.getvalue())

    def test_legacy_boxes_are_not_scored_as_floor(self):
        case = {
            "message": "Tengo una cama y unas 15 cajas",
            "state": {
                "service": None,
                "locations": {
                    "origin": {"floor": None},
                    "destination": {"floor": None},
                },
                "load": None,
            },
            "expected": {"load": "cama 15 cajas"},
            "forbidden": {
                "locations.origin.floor": 15,
                "locations.destination.floor": 15,
            },
        }

        state, changed, ambiguities = legacy_result(case)
        result = score(case, state, changed, ambiguities)

        self.assertTrue(result["semantic_safe"])
        self.assertNotIn("locations.origin.floor", changed)
        self.assertNotIn("locations.destination.floor", changed)
