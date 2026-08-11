import copy
import hashlib
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from .blind_holdout import blind_holdout_cases
from .delta_context import DeltaContext
from .delta_extractor import extract_conversation_delta
from .delta_snapshot import CanonicalSnapshot
from .delta_validator_v2 import validate_delta_v2
from .management.commands.compare_delta_shadow import _apply_v2, _get, _matches, aggregate, score


LEAD_PATHS = {
    "service": "service", "load": "load", "staff_required": "staff.required",
    "packing": "additional_services.packing",
    "packing_required": "additional_services.packing_required",
    "packing_mode": "additional_services.packing",
    "disassembly_required": "additional_services.disassembly_required",
    "assembly_required": "additional_services.assembly_required",
}


def dataset_sha256(cases=None):
    payload = json.dumps(cases or blind_holdout_cases(), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _safe(value):
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"[\w.+-]+@[\w.-]+", "[redacted-email]", value)
        value = re.sub(r"\b(?:\+?51)?9\d{8}\b", "[redacted-phone]", value)
        value = re.sub(r"\b\d{8}\b", "[redacted-document]", value)
    return value


def flatten_delta(delta):
    result = {}
    for field, proposal in delta.changes.lead:
        if proposal is not None:
            result[LEAD_PATHS[field]] = {
                "field": field, "location": None, "value": proposal.value,
                "evidence": proposal.evidence,
                "evidence_type": proposal.evidence_type.value,
                "source": "customer_message" if proposal.evidence_type.value == "explicit"
                else "contextual_reply",
            }
    for index, location in enumerate(delta.changes.locations):
        refs = ["origin", "destination"] if location.ref == "both" else [location.ref]
        for ref in refs:
            for field, proposal in location.set:
                if proposal is not None:
                    result[f"locations.{ref}.{field}"] = {
                        "field": field, "location": ref, "source_ref": location.ref,
                        "location_index": index, "value": proposal.value,
                        "evidence": proposal.evidence,
                        "evidence_type": proposal.evidence_type.value,
                        "ref_evidence": location.ref_evidence,
                        "ref_evidence_type": location.ref_evidence_type.value,
                        "source": "customer_message" if proposal.evidence_type.value == "explicit"
                        else "contextual_reply",
                    }
    return result


def _failure_details(case, state, changed, flattened, ambiguities):
    false_positives, false_negatives = [], []
    for path, value in case.get("expected", {}).items():
        if not _matches(_get(state, path), value):
            false_negatives.append({"path": path, "expected": value,
                                    "actual": _get(state, path)})
    for path, value in case.get("forbidden", {}).items():
        if _matches(_get(state, path), value):
            false_positives.append({"path": path, "proposal": flattened.get(path),
                                    "why": "forbidden_value", "forbidden": value})
    expected_paths = set(case.get("expected", {}))
    for path, value in changed.items():
        if path not in expected_paths and _get(case["state"], path) != value:
            false_positives.append({"path": path, "proposal": flattened.get(path),
                                    "why": "unrequested_state_change"})
    for field in case.get("expected_ambiguities", []):
        if not any(field in item for item in ambiguities):
            false_negatives.append({"path": f"ambiguity:{field}", "expected": field,
                                    "actual": None})
    return false_positives, false_negatives


def _rejected_detail(item, raw_flat, raw_delta):
    proposal = raw_flat.get(item.path)
    if proposal is None:
        match = re.match(r"changes\.locations\[(\d+)](?:\.set\.(\w+)|\.ref)", item.path)
        if match:
            index, field = int(match.group(1)), match.group(2)
            candidates = [value for value in raw_flat.values()
                          if value.get("location_index") == index
                          and (field is None or value.get("field") == field)]
            proposal = candidates[0] if len(candidates) == 1 else candidates
    return {"path": item.path, "proposal": proposal, "reason_code": item.reason}


def evaluate_case(case, request_number):
    snapshot = CanonicalSnapshot(state_version=f"blind:{case['id']}", state=case["state"])
    payload = {
        "state_version": snapshot.state_version, "state": snapshot.state,
        "last_bot_question": case.get("last_bot_question", ""),
        "customer_message": case["message"], "recent_turns": case.get("recent_turns", []),
    }
    context = DeltaContext(payload=payload,
                           last_bot_question=case.get("last_bot_question", ""),
                           recent_turn_count=len(case.get("recent_turns", [])))
    delta, metrics = extract_conversation_delta(context, provider_name="openai")
    validation = validate_delta_v2(
        delta, snapshot, customer_message=case["message"],
        last_bot_question=context.last_bot_question,
        expected_state_version=snapshot.state_version,
    )
    raw_state, raw_changed = _apply_v2(copy.deepcopy(case["state"]), delta)
    accepted_state, accepted_changed = _apply_v2(copy.deepcopy(case["state"]), validation.accepted)
    raw_flat, accepted_flat = flatten_delta(delta), flatten_delta(validation.accepted)
    raw_ambiguities = [item.field for item in delta.ambiguities]
    accepted_ambiguities = [item.field for item in validation.accepted.ambiguities]
    raw_fp, raw_fn = _failure_details(case, raw_state, raw_changed, raw_flat, raw_ambiguities)
    accepted_fp, accepted_fn = _failure_details(
        case, accepted_state, accepted_changed, accepted_flat, accepted_ambiguities)
    raw_score = score(case, raw_state, raw_changed, raw_ambiguities, delta.corrections)
    accepted_score = score(case, accepted_state, accepted_changed,
                           accepted_ambiguities, validation.accepted.corrections)
    record = {
        "case_id": case["id"],
        "case_type": "real" if case["source"].startswith("historical") else "synthetic",
        "multiturn": case["multiturn"],
        "input_metadata": {"snapshot_version": snapshot.state_version,
                           "last_question_present": bool(context.last_bot_question),
                           "recent_turn_count": context.recent_turn_count},
        "raw_model_delta": delta.model_dump(mode="json", exclude_none=True),
        "raw_proposals": raw_flat,
        "validator": {
            "accepted_delta": validation.accepted.model_dump(mode="json", exclude_none=True),
            "accepted_proposals": accepted_flat,
            "rejected_changes": [_rejected_detail(item, raw_flat, delta)
                                 for item in validation.rejected],
            "latency_ms": validation.latency_ms,
        },
        "evaluation": {
            "expected_delta_or_state": case.get("expected", {}),
            "forbidden": case.get("forbidden", {}),
            "expected_ambiguities": case.get("expected_ambiguities", []),
            "raw_false_positives": raw_fp, "raw_false_negatives": raw_fn,
            "accepted_false_positives": accepted_fp,
            "accepted_false_negatives": accepted_fn,
            "semantic_safe_raw": raw_score["semantic_safe"],
            "semantic_safe_accepted": accepted_score["semantic_safe"],
            "raw_score": raw_score, "accepted_score": accepted_score,
        },
        "usage": {"input_tokens": metrics.input_tokens or 0,
                  "output_tokens": metrics.output_tokens or 0,
                  "total_tokens": (metrics.input_tokens or 0) + (metrics.output_tokens or 0)},
        "latency_ms": metrics.latency_ms, "provider": metrics.provider,
        "model": metrics.model, "schema_version": 2, "validator_version": 2,
        "request_number": request_number,
    }
    return _safe(record), raw_score, accepted_score


def run_evidence_cases(cases, output_root, *, run_suffix="delta_v2_evidence"):
    timestamp = datetime.now(timezone.utc)
    run_id = timestamp.strftime("%Y%m%dT%H%M%SZ") + f"_{run_suffix}"
    run_dir = Path(output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    start_hash = dataset_sha256(blind_holdout_cases())
    manifest = {
        "run_id": run_id, "timestamp": timestamp.isoformat(),
        "git_head": __import__("subprocess").check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip(),
        "dataset_sha256": start_hash, "prompt_version": 2, "schema_version": 2,
        "validator_version": 2, "provider": "openai",
        "model": settings.OPENAI_EXTRACTION_MODEL, "case_count": len(cases),
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    records, raw_scores, accepted_scores = [], [], []
    with (run_dir / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for number, case in enumerate(cases, 1):
            record, raw_score, accepted_score = evaluate_case(case, number)
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            records.append(record); raw_scores.append({"score": raw_score})
            accepted_scores.append({"score": accepted_score})
    end_hash = dataset_sha256(blind_holdout_cases())
    latencies = [item["latency_ms"] for item in records]
    summary = {
        "run_id": run_id, "dataset_hash_start": start_hash,
        "dataset_hash_end": end_hash, "dataset_hash_match": start_hash == end_hash,
        "records_written": len(records), "api_successes": len(records),
        "schema_valid": len(records), "raw": aggregate(raw_scores),
        "accepted": aggregate(accepted_scores),
        "tokens": {key: sum(item["usage"][key] for item in records)
                   for key in ("input_tokens", "output_tokens", "total_tokens")},
        "latency": {"average_ms": statistics.mean(latencies),
                    "p50_ms": statistics.median(latencies),
                    "p95_ms": sorted(latencies)[max(0, round(len(latencies) * .95) - 1)],
                    "max_ms": max(latencies)},
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return run_dir, summary


def read_evidence_run(run_dir):
    run_dir = Path(run_dir)
    records = [json.loads(line) for line in
               (run_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    return (json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8")),
            json.loads((run_dir / "summary.json").read_text(encoding="utf-8")), records)
