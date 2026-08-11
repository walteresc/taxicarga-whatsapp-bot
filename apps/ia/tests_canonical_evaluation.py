from django.test import SimpleTestCase

from .canonical_evaluation import (
    ORIGINAL_FN_CAUSES, PACKING_ADJUDICATION, REJECTION_AUDIT,
    canonical_score, canonicalize_actual, canonicalize_expected,
)


class CanonicalEvaluationTests(SimpleTestCase):
    def case(self, expected=None, case_id="x"):
        return {"id":case_id, "expected":expected or {}, "forbidden":{},
                "expected_ambiguities":[], "expected_correction":False,
                "state":{"additional_services":{"packing":None}}}

    def delta(self, lead):
        return {"changes":{"lead":lead,"locations":[]},
                "corrections":[],"ambiguities":[]}

    def test_specific_legacy_packing_equals_v3_required_and_mode(self):
        case = self.case({"additional_services.packing":"embalaje full"})
        delta = self.delta({
            "packing_required":{"value":True},
            "packing_mode":{"value":"embalaje full"},
        })
        self.assertTrue(canonical_score(case, delta)["correct"])

    def test_without_packing_equals_required_false_without_mode(self):
        case = self.case({"additional_services.packing":"sin embalaje"})
        delta = self.delta({"packing_required":{"value":False}})
        self.assertTrue(canonical_score(case, delta)["correct"])

    def test_required_does_not_invent_specific_mode(self):
        case = self.case({"additional_services.packing":"embalaje basico"})
        delta = self.delta({"packing_required":{"value":True}})
        score = canonical_score(case, delta)
        self.assertFalse(score["correct"])
        self.assertIn("missing:packing.mode", score["errors"])

    def test_adjudication_is_separate_from_original_label(self):
        case = self.case({}, case_id="r08")
        self.assertEqual(case["expected"], {})
        self.assertEqual(canonicalize_expected(case), {"packing.required":True})

    def test_canonical_actual_never_mutates_delta(self):
        delta = self.delta({"packing_mode":{"value":"sin embalaje"}})
        before = repr(delta)
        canonicalize_actual(delta)
        self.assertEqual(repr(delta), before)

    def test_adjudication_accounting_is_complete(self):
        self.assertEqual(len(PACKING_ADJUDICATION), 9)
        self.assertEqual(sum(ORIGINAL_FN_CAUSES.values()), 43)
        self.assertEqual(sum(item["correct"] + item["false"]
                             for item in REJECTION_AUDIT.values()), 34)
