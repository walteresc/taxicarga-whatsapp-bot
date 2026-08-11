import copy
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import openai
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ia.blind_holdout import blind_holdout_cases
from apps.ia.delta_context import DeltaContext
from apps.ia.delta_extractor import extract_conversation_delta
from apps.ia.delta_snapshot import CanonicalSnapshot
from apps.ia.delta_validator_v2 import validate_delta_v2
from apps.ia.management.commands.compare_delta_shadow import (
    _apply_v2, aggregate, legacy_result, score,
    GPT41_MINI_INPUT_USD_PER_MILLION, GPT41_MINI_OUTPUT_USD_PER_MILLION,
)


def _percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile / 100
    low, high = math.floor(index), math.ceil(index)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def _correlation(xs, ys):
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return statistics.correlation(xs, ys)


def _instrumented_result(case, request_number):
    snapshot = CanonicalSnapshot(state_version=f"blind:{case['id']}", state=case["state"])
    payload = {
        "state_version": snapshot.state_version,
        "state": snapshot.state,
        "last_bot_question": case.get("last_bot_question", ""),
        "customer_message": case["message"],
        "recent_turns": case.get("recent_turns", []),
    }
    context = DeltaContext(
        payload=payload,
        last_bot_question=case.get("last_bot_question", ""),
        recent_turn_count=len(case.get("recent_turns", [])),
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    delta, metrics = extract_conversation_delta(context, provider_name="openai")
    validation = validate_delta_v2(
        delta, snapshot, customer_message=case["message"],
        last_bot_question=case.get("last_bot_question", ""),
        expected_state_version=snapshot.state_version,
    )
    raw_state, raw_changed = _apply_v2(copy.deepcopy(case["state"]), delta)
    accepted_state, accepted_changed = _apply_v2(copy.deepcopy(case["state"]), validation.accepted)
    raw_score = score(case, raw_state, raw_changed, [x.field for x in delta.ambiguities], delta.corrections)
    accepted_score = score(
        case, accepted_state, accepted_changed,
        [x.field for x in validation.accepted.ambiguities], validation.accepted.corrections,
    )
    request = {
        "request_number": request_number,
        "timestamp": timestamp,
        "input_tokens": metrics.input_tokens or 0,
        "output_tokens": metrics.output_tokens or 0,
        "provider_latency_ms": metrics.latency_ms,
        "parse_structured_output_latency_ms": None,
        "validator_latency_ms": validation.latency_ms,
        "success": True, "error": None, "retry_count": None,
        "provider_status": "success",
        "snapshot_bytes": len(json.dumps(snapshot.state, ensure_ascii=False)),
        "recent_turns": context.recent_turn_count,
        "location_deltas": len(delta.changes.locations),
    }
    return {
        "raw": {"id": case["id"], "score": raw_score},
        "accepted": {"id": case["id"], "score": accepted_score,
                     "rejected": [{"path": x.path, "reason": x.reason} for x in validation.rejected]},
        "request": request,
    }


class Command(BaseCommand):
    help = "Ejecuta holdout ciego IA-first V2 y prueba controlada de latencia."

    def add_arguments(self, parser):
        parser.add_argument("--validate-only", action="store_true")
        parser.add_argument("--confirm-real-api", action="store_true")
        parser.add_argument("--repeat-latency", action="store_true")
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options):
        cases = blind_holdout_cases()
        if len(cases) != 100 or len({x["id"] for x in cases}) != 100:
            raise CommandError("Holdout debe contener 100 IDs únicos.")
        if options["validate_only"]:
            self.stdout.write(self.style.SUCCESS(
                f"Holdout válido: {len(cases)}; reales={sum(x['source'].startswith('historical') for x in cases)}; "
                f"multiturno={sum(x['multiturn'] for x in cases)}; cero APIs."
            ))
            return
        if not options["confirm_real_api"]:
            raise CommandError("Use --confirm-real-api para autorizar OpenAI real.")

        legacy, raw, accepted, requests = [], [], [], []
        for number, case in enumerate(cases, 1):
            legacy_state, legacy_changed, legacy_ambiguities = legacy_result(case)
            legacy.append({"id": case["id"], "score": score(
                case, legacy_state, legacy_changed, legacy_ambiguities, [])})
            try:
                result = _instrumented_result(case, number)
                raw.append(result["raw"]); accepted.append(result["accepted"])
                requests.append(result["request"])
            except Exception as exc:
                failed_score = {"tp": 0, "fp": 0, "fn": len(case["expected"]),
                                "correct": False, "semantic_safe": True,
                                "ambiguity_ok": False, "errors": ["api_or_schema_error"]}
                raw.append({"id": case["id"], "score": failed_score})
                accepted.append({"id": case["id"], "score": copy.deepcopy(failed_score), "rejected": []})
                requests.append({"request_number": number, "timestamp": datetime.now(timezone.utc).isoformat(),
                                 "success": False, "error": type(exc).__name__,
                                 "retry_count": None, "provider_status": getattr(exc, "status_code", None)})

        repeated = []
        if options["repeat_latency"]:
            selected = [cases[i] for i in (0, 3, 10, 14, 18, 22, 27, 37, 46, 54)]
            next_number = len(requests) + 1
            for run in range(1, 4):
                for case in selected:
                    try:
                        item = _instrumented_result(case, next_number)["request"]
                        item.update({"case_id": case["id"], "run": run})
                        repeated.append(item)
                    except Exception as exc:
                        repeated.append({"request_number": next_number, "case_id": case["id"], "run": run,
                                         "success": False, "error": type(exc).__name__,
                                         "provider_status": getattr(exc, "status_code", None), "retry_count": None})
                    next_number += 1

        successful = [x for x in requests if x.get("success")]
        latencies = [x["provider_latency_ms"] for x in successful]
        buckets = Counter()
        for value in latencies:
            buckets["<3s" if value < 3000 else "3-5s" if value < 5000 else
                    "5-10s" if value < 10000 else "10-20s" if value < 20000 else
                    "20-30s" if value < 30000 else ">30s"] += 1
        correct_rejections = false_rejections = accepted_unsafe = 0
        rejection_reasons = Counter()
        for raw_item, accepted_item in zip(raw, accepted):
            rejection_reasons.update(x["reason"] for x in accepted_item.get("rejected", []))
            if raw_item["score"]["fp"] > accepted_item["score"]["fp"]:
                correct_rejections += raw_item["score"]["fp"] - accepted_item["score"]["fp"]
            if accepted_item["score"]["fn"] > raw_item["score"]["fn"]:
                false_rejections += accepted_item["score"]["fn"] - raw_item["score"]["fn"]
            accepted_unsafe += accepted_item["score"]["fp"]
        input_tokens = sum(x["input_tokens"] for x in successful) + sum(x.get("input_tokens", 0) for x in repeated)
        output_tokens = sum(x["output_tokens"] for x in successful) + sum(x.get("output_tokens", 0) for x in repeated)
        input_rate = settings.OPENAI_INPUT_USD_PER_MILLION or GPT41_MINI_INPUT_USD_PER_MILLION
        output_rate = settings.OPENAI_OUTPUT_USD_PER_MILLION or GPT41_MINI_OUTPUT_USD_PER_MILLION
        cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
        report = {
            "holdout": {"total": 100, "real": 40, "synthetic": 60,
                        "multiturn": sum(x["multiturn"] for x in cases),
                        "evaluation_valid": len(successful) == len(cases),
                        "expected_labels_available_to_model": False,
                        "expected_labels_available_to_validator": False},
            "legacy": aggregate(legacy), "raw": aggregate(raw), "accepted": aggregate(accepted),
            "validator": {"correct_rejections": correct_rejections,
                          "false_rejections": false_rejections,
                          "accepted_unsafe": accepted_unsafe,
                          "reasons": dict(rejection_reasons)},
            "latency": {"average_ms": statistics.mean(latencies) if latencies else None,
                        **{f"p{p}_ms": _percentile(latencies, p) for p in (50, 75, 90, 95, 99)},
                        "max_ms": max(latencies) if latencies else None,
                        "buckets": dict(buckets)},
            "correlations": {
                "input_tokens": _correlation([x["input_tokens"] for x in successful], latencies),
                "output_tokens": _correlation([x["output_tokens"] for x in successful], latencies),
                "snapshot_bytes": _correlation([x["snapshot_bytes"] for x in successful], latencies),
                "recent_turns": _correlation([x["recent_turns"] for x in successful], latencies),
                "location_deltas": _correlation([x["location_deltas"] for x in successful], latencies),
            },
            "requests": requests, "repeated_prompt_requests": repeated,
            "client": {"new_client_each_request": True,
                       "connection_pool_reused_across_requests": False,
                       "sdk_default_max_retries": openai.DEFAULT_MAX_RETRIES,
                       "configured_timeout_seconds": settings.AI_REQUEST_TIMEOUT_SECONDS,
                       "observed_retry_count_available": False},
            "tokens": {"input": input_tokens, "output": output_tokens,
                       "total": input_tokens + output_tokens,
                       "average_input_holdout": input_tokens / max(1, len(successful) + len(repeated))},
            "cost": {"total_extraction_usd": cost,
                     "per_1000_extractions_usd": cost / max(1, len(successful) + len(repeated)) * 1000,
                     "per_10000_extractions_usd": cost / max(1, len(successful) + len(repeated)) * 10000,
                     "response_generation_included": False},
        }
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if options["output"]:
            options["output"].write_text(rendered + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Reporte guardado: {options['output']}"))
        else:
            self.stdout.write(rendered)
