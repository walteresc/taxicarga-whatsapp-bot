import copy
import json
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from .benchmark_cost import openai_benchmark_cost
from .delta_context import DeltaContext
from .delta_extractor_v3 import extract_conversation_delta_v3
from .delta_snapshot import CanonicalSnapshot
from .delta_validator_v3 import validate_delta_v3
from .evidence_artifacts import (
    _failure_details, _rejected_detail, _safe, dataset_sha256, flatten_delta,
)
from .management.commands.compare_delta_shadow import _apply_v2, aggregate, score


def evaluate_v3_case(case, request_number):
    snapshot = CanonicalSnapshot(f"v3-development:{case['id']}", case["state"])
    targets = tuple(case.get("question_targets") or ())
    payload = {
        "state_version": snapshot.state_version, "state": snapshot.state,
        "last_bot_question": case.get("last_bot_question") or None,
        "last_question_targets": list(targets),
        "customer_message": case["message"],
        "recent_turns": case.get("recent_turns", []),
    }
    context = DeltaContext(payload, case.get("last_bot_question", ""),
                           len(payload["recent_turns"]), targets)
    delta, metrics = extract_conversation_delta_v3(context, provider_name="openai")
    validation = validate_delta_v3(
        delta, snapshot, customer_message=case["message"],
        question_targets=targets, expected_state_version=snapshot.state_version,
    )
    raw_state, raw_changed = _apply_v2(copy.deepcopy(case["state"]), delta)
    accepted_state, accepted_changed = _apply_v2(
        copy.deepcopy(case["state"]), validation.accepted)
    raw_flat, accepted_flat = flatten_delta(delta), flatten_delta(validation.accepted)
    raw_ambiguities = [item.field for item in delta.ambiguities]
    accepted_ambiguities = [item.field for item in validation.accepted.ambiguities]
    raw_fp, raw_fn = _failure_details(
        case, raw_state, raw_changed, raw_flat, raw_ambiguities)
    accepted_fp, accepted_fn = _failure_details(
        case, accepted_state, accepted_changed, accepted_flat, accepted_ambiguities)
    raw_score = score(case, raw_state, raw_changed, raw_ambiguities, delta.corrections)
    accepted_score = score(case, accepted_state, accepted_changed,
                           accepted_ambiguities, validation.accepted.corrections)
    record = {
        "case_id": case["id"], "dataset_role": "V3_DEVELOPMENT_SET",
        "input": {"state": snapshot.state,
                  "last_bot_question": context.last_bot_question,
                  "question_targets": list(targets),
                  "customer_message": case["message"],
                  "recent_turns": payload["recent_turns"]},
        "target_metadata_status": case["target_metadata_status"],
        "raw_v3_delta": delta.model_dump(mode="json", exclude_none=True),
        "accepted_v3_delta": validation.accepted.model_dump(mode="json", exclude_none=True),
        "rejections": [_rejected_detail(item, raw_flat, delta)
                       for item in validation.rejected],
        "evaluation": {"expected": case.get("expected", {}),
                       "raw_false_positives": raw_fp, "raw_false_negatives": raw_fn,
                       "accepted_false_positives": accepted_fp,
                       "accepted_false_negatives": accepted_fn,
                       "safety_raw": raw_score["semantic_safe"],
                       "safety_accepted": accepted_score["semantic_safe"],
                       "raw_score": raw_score, "accepted_score": accepted_score},
        "usage": {"input_tokens": metrics.input_tokens or 0,
                  "output_tokens": metrics.output_tokens or 0,
                  "total_tokens": (metrics.input_tokens or 0) + (metrics.output_tokens or 0)},
        "latency_ms": metrics.latency_ms, "provider": metrics.provider,
        "model": metrics.model, "schema_version": 3, "validator_version": 3,
        "request_number": request_number,
    }
    return _safe(record), raw_score, accepted_score


def run_v3_cases(cases, output_root, *, run_suffix="v3_smoke"):
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + f"_{run_suffix}"
    run_dir = Path(output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "run_id": run_id, "timestamp": now.isoformat(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "dataset_role": "V3_DEVELOPMENT_SET", "dataset_sha256": dataset_sha256(cases),
        "prompt_version": 3, "schema_version": 3, "validator_version": 3,
        "provider": "openai", "model": settings.OPENAI_EXTRACTION_MODEL,
        "case_ids": [case["id"] for case in cases], "case_count": len(cases),
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    records, raw_scores, accepted_scores = [], [], []
    with (run_dir / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for number, case in enumerate(cases, 1):
            try:
                record, raw_score, accepted_score = evaluate_v3_case(case, number)
            except Exception as exc:
                failure = {
                    "case_id": case["id"], "request_number": number,
                    "error_type": type(exc).__name__,
                    "http_status": getattr(exc, "status_code", None),
                    "error_code": ((getattr(exc, "body", None) or {}).get("error") or {}).get("code"),
                    "message": "sanitized; credentials omitted",
                }
                (run_dir / "failure.json").write_text(
                    json.dumps(failure, indent=2) + "\n", encoding="utf-8")
                (run_dir / "summary.json").write_text(json.dumps({
                    "run_id": run_id, "records_written": len(records),
                    "api_calls_attempted": number, "schema_valid": len(records),
                    "gate": "FAIL", "failed_case": case["id"],
                }, indent=2) + "\n", encoding="utf-8")
                raise
            stream.write(json.dumps(record, ensure_ascii=False) + "\n"); stream.flush()
            records.append(record); raw_scores.append({"score": raw_score})
            accepted_scores.append({"score": accepted_score})
    latencies = [row["latency_ms"] for row in records]
    tokens = {key: sum(row["usage"][key] for row in records)
              for key in ("input_tokens", "output_tokens", "total_tokens")}
    summary = {
        "run_id": run_id, "records_written": len(records),
        "api_calls": len(records), "schema_valid": len(records),
        "question_target_included": all(row["input"]["question_targets"] for row in records),
        "raw": aggregate(raw_scores), "accepted": aggregate(accepted_scores),
        "tokens": tokens,
        "cost": openai_benchmark_cost(tokens["input_tokens"], tokens["output_tokens"]),
        "latency": {"average_ms": statistics.mean(latencies),
                    "p50_ms": statistics.median(latencies), "max_ms": max(latencies)},
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return run_dir, summary
