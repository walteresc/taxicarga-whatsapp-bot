import copy

from .blind_holdout import blind_holdout_cases


# Curated from each bot turn's construction objective. Never derived from expected.
QUESTION_TARGETS_BY_CASE = {
    "r04": [("floor", "both")], "r05": [("elevator", "origin")],
    "r06": [("elevator", "destination")], "r07": [("staff_required", None)],
    "r08": [("packing_required", None)], "r09": [("packing_mode", None)],
    "r10": [("packing_mode", None)], "r11": [("packing_mode", None)],
    "r12": [("packing_mode", None)], "r14": [("staff_required", None)],
    "r16": [("packing_required", None)], "r17": [("staff_required", None)],
    "r18": [("packing_required", None)], "r21": [("floor", "both")],
    "r22": [("elevator", "both")], "r23": [("packing_required", None)],
    "r24": [("disassembly_required", None)], "r25": [("service_date", None)],
    "r31": [("floor", "both")], "r32": [("elevator", "origin")],
    "r33": [("elevator", "destination")], "r34": [("staff_required", None)],
    "r35": [("packing_mode", None)], "r36": [("assembly_required", None)],
    "r38": [("staff_required", None)], "r39": [("packing_required", None)],
    "r40": [("elevator", "both")], "s08": [("floor", "both")],
    "s11": [("elevator", "origin")], "s12": [("elevator", "destination")],
    "s13": [("truck_access", "origin")],
    "s14": [("truck_access", "destination")],
    "s15": [("elevator", "both")], "s16": [("elevator", "origin")],
    "s17": [("elevator", "origin")], "s18": [("access_observation", None)],
    "s21": [("elevator", "both")], "s22": [("elevator", "both")],
    "s47": [("truck_access", "both")], "s48": [("elevator", "both")],
    "s49": [("truck_access", "both")],
    "s50": [("district", "destination")],
    "s54": [("load", None), ("floor", "origin")],
    "s57": [("elevator", "both")], "s58": [("elevator", "both")],
}


def v3_development_cases():
    cases = copy.deepcopy(blind_holdout_cases())
    for case in cases:
        raw = QUESTION_TARGETS_BY_CASE.get(case["id"])
        case["question_targets"] = (
            [{"field": field, "ref": ref, "operation": "set"} for field, ref in raw]
            if raw else []
        )
        case["target_metadata_status"] = (
            "AVAILABLE" if raw else
            ("TARGET_METADATA_UNAVAILABLE" if case["last_bot_question"] else "NOT_APPLICABLE")
        )
        case["dataset_role"] = "V3_DEVELOPMENT_SET"
        case["label_review_required"] = case["id"] == "s02"
    return cases
