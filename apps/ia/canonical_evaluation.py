"""Offline-only semantic scoring for persisted V3 evaluation artifacts."""

import copy

from .management.commands.compare_delta_shadow import _matches


LEAD_PATHS = {
    "service": "service", "load": "load", "staff_required": "staff.required",
    "disassembly_required": "additional_services.disassembly_required",
    "assembly_required": "additional_services.assembly_required",
}

# Adjudication layer only. Original labels remain immutable.
EXPECTED_ADJUDICATIONS = {
    "r08": {"packing.required": True},
    "r18": {"packing.required": True},
}

HUMAN_REVIEW_CASES = {
    "s02": "'carga comercial' may name service, cargo, or both",
    "s16": "'en el otro' conflicts with origin-only target metadata",
    "s25": "parking at door does not unambiguously equal truck entry",
    "s53": "elevator capacity is not clearly transported load",
}

PACKING_ADJUDICATION = {
    "r08": "EXPECTED_LABEL_ERROR", "r10": "REPRESENTATION_MISMATCH",
    "r11": "REPRESENTATION_MISMATCH", "r16": "REPRESENTATION_MISMATCH",
    "r18": "EXPECTED_LABEL_ERROR", "r23": "REPRESENTATION_MISMATCH",
    "r39": "REPRESENTATION_MISMATCH",
    "s30": "REPRESENTATION_MISMATCH+MODEL_ERROR_CORRECTION",
    "s34": "REPRESENTATION_MISMATCH",
}

ACCEPTED_UNSAFE_ADJUDICATION = {
    "r08": ("EXPECTED_LABEL_ERROR", "packing-required fact absent from legacy label"),
    "r10": ("REPRESENTATION_MISMATCH", "required=false duplicates legacy no-packing mode"),
    "r11": ("REPRESENTATION_MISMATCH", "required=true accompanies specific mode"),
    "r14": ("MODEL_ERROR", "staff answer mislabeled as explicit service"),
    "r16": ("REPRESENTATION_MISMATCH", "required=false fully expresses no packing"),
    "r17": ("MODEL_ERROR", "staff answer mislabeled as explicit service"),
    "r18": ("EXPECTED_LABEL_ERROR", "contextual packing-required fact omitted by label"),
    "r23": ("REPRESENTATION_MISMATCH", "required=false fully expresses no packing"),
    "r27": ("MODEL_ERROR", "quantity complaint mislabeled as transported load"),
    "r30": ("MODEL_ERROR", "route-only message invented service"),
    "r39": ("REPRESENTATION_MISMATCH", "required=false fully expresses no packing"),
    "s02": ("HUMAN_REVIEW", "commercial may qualify service or cargo"),
    "s13": ("TARGET_METADATA_ERROR+MODEL_ERROR", "truck question stored as observation target"),
    "s14": ("TARGET_METADATA_ERROR+MODEL_ERROR", "truck question stored as observation target"),
    "s18": ("VALIDATOR_ERROR", "endpoint-free observation accepted as origin"),
    "s20": ("MODEL_ERROR", "who loads was stored as transported load"),
    "s30": ("REPRESENTATION_MISMATCH+MODEL_ERROR", "state matches; correction metadata missing"),
    "s34": ("REPRESENTATION_MISMATCH", "required=true accompanies specific mode"),
}

REJECTION_AUDIT = {
    "CONTEXT_TARGET_MISMATCH": {"correct": 4, "false": 14},
    "ATTRIBUTE_CLOSURE": {"correct": 8, "false": 0},
    "NO_EVIDENCE": {"correct": 5, "false": 0},
    "AMBIGUOUS_REF": {"correct": 1, "false": 1},
    "DERIVED_FIELD_FORBIDDEN": {"correct": 0, "false": 1},
}

ORIGINAL_FN_CAUSES = {
    "representation_mismatch": 3,
    "validator_false_rejection": 14,
    "target_metadata_error": 5,
    "schema_coverage_gap": 3,
    "expected_or_human_review": 2,
    "model_error_or_omission": 16,
}


def _canonical_packing(value):
    if value == "sin embalaje":
        return {"packing.required": False}
    if value in {
        "embalaje basico", "embalaje de muebles y artefactos", "embalaje full"
    }:
        return {"packing.required": True, "packing.mode": value}
    if value == "con embalaje":
        return {"packing.required": True}
    return {"packing.mode": value}


def canonicalize_expected(case):
    result = {}
    for path, value in case.get("expected", {}).items():
        if path == "additional_services.packing":
            result.update(_canonical_packing(value))
        else:
            result[path] = value
    result.update(EXPECTED_ADJUDICATIONS.get(case["id"], {}))
    return result


def canonicalize_forbidden(case):
    result = {}
    for path, value in case.get("forbidden", {}).items():
        if path == "additional_services.packing":
            result.update(_canonical_packing(value))
        else:
            result[path] = value
    return result


def canonicalize_actual(delta):
    result = {}
    lead = delta.get("changes", {}).get("lead", {})
    for field, path in LEAD_PATHS.items():
        if field in lead:
            result[path] = lead[field]["value"]
    if "packing_required" in lead:
        result["packing.required"] = lead["packing_required"]["value"]
    if "packing_mode" in lead:
        result.update(_canonical_packing(lead["packing_mode"]["value"]))
    for location in delta.get("changes", {}).get("locations", []):
        refs = ("origin", "destination") if location["ref"] == "both" else (location["ref"],)
        for ref in refs:
            for field, proposal in location.get("set", {}).items():
                result[f"locations.{ref}.{field}"] = proposal["value"]
    return result


def canonical_score(case, delta):
    expected = canonicalize_expected(case)
    forbidden = canonicalize_forbidden(case)
    actual = canonicalize_actual(delta)
    tp = sum(_matches(actual.get(path), value) for path, value in expected.items())
    fn_paths = [path for path, value in expected.items()
                if not _matches(actual.get(path), value)]
    fp_paths = [path for path, value in actual.items()
                if path not in expected and not _matches(_state_value(case["state"], path), value)]
    forbidden_paths = [path for path, value in forbidden.items()
                       if _matches(actual.get(path), value)]
    expected_ambiguities = case.get("expected_ambiguities", [])
    actual_ambiguities = [item["field"] for item in delta.get("ambiguities", [])]
    missing_ambiguities = [field for field in expected_ambiguities
                           if not any(field in item for item in actual_ambiguities)]
    correction_missing = bool(case.get("expected_correction") and not delta.get("corrections"))
    fn = len(fn_paths) + len(missing_ambiguities) + int(correction_missing)
    fp = len(fp_paths) + len(forbidden_paths)
    errors = ([f"missing:{path}" for path in fn_paths]
              + [f"extra:{path}" for path in fp_paths]
              + [f"forbidden:{path}" for path in forbidden_paths]
              + [f"ambiguity_missing:{field}" for field in missing_ambiguities]
              + (["correction_missing"] if correction_missing else []))
    return {
        "tp": tp, "fp": fp, "fn": fn, "correct": not errors,
        "semantic_safe": fp == 0 and not forbidden_paths,
        "expected": expected, "actual": actual, "errors": errors,
    }


def aggregate_canonical(scores):
    tp = sum(item["tp"] for item in scores)
    fp = sum(item["fp"] for item in scores)
    fn = sum(item["fn"] for item in scores)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    return {
        "cases": len(scores), "correct_cases": sum(item["correct"] for item in scores),
        "safe_cases": sum(item["semantic_safe"] for item in scores),
        "tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
    }


def _state_value(state, path):
    value = state
    aliases = {"packing": "additional_services.packing"}
    if path == "packing.required":
        packing = _state_value(state, aliases["packing"])
        return None if packing is None else packing != "sin embalaje"
    if path == "packing.mode":
        packing = _state_value(state, aliases["packing"])
        return packing if packing and packing != "sin embalaje" else None
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value
