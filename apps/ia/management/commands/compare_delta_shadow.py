import copy
import difflib
import json
import statistics
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ia.data_extractor import extract_lead_data
from apps.ia.delta_context import DeltaContext
from apps.ia.delta_extractor import extract_conversation_delta
from apps.ia.delta_snapshot import CanonicalSnapshot
from apps.ia.delta_validator_v2 import validate_delta_v2


DATASET_PATH = Path(__file__).resolve().parents[2] / "tests_data" / "delta_shadow_dataset.json"
GPT41_MINI_INPUT_USD_PER_MILLION = 0.40
GPT41_MINI_OUTPUT_USD_PER_MILLION = 1.60


def _norm(value):
    if not isinstance(value, str):
        return value
    return " ".join(
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower().split()
    )


def _matches(actual, expected):
    if not isinstance(expected, str):
        return actual == expected
    actual_words = set(_norm(actual or "").replace(",", " ").split())
    expected_words = set(_norm(expected).replace(",", " ").split())
    matched = sum(
        any(word in candidate or candidate in word or difflib.SequenceMatcher(None, word, candidate).ratio() >= .72
            for candidate in actual_words)
        for word in expected_words
    )
    return bool(expected_words) and matched / len(expected_words) >= 0.6


def _get(state, path):
    value = state
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _set(state, path, value):
    target = state
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


LEGACY_MAP = {
    "tipo_servicio": "service",
    "distrito_origen": "locations.origin.district",
    "distrito_destino": "locations.destination.district",
    "piso_origen": "locations.origin.floor",
    "piso_destino": "locations.destination.floor",
    "ascensor_origen": "locations.origin.elevator",
    "ascensor_destino": "locations.destination.elevator",
    "lista_objetos": "load",
    "incluye_personal_carga": "staff.required",
    "modalidad_servicio": "additional_services.packing",
    "requiere_desarmado": "additional_services.disassembly_required",
    "requiere_armado": "additional_services.assembly_required",
    "camion_llega_origen": "locations.origin.truck_access",
    "camion_llega_destino": "locations.destination.truck_access",
    "distancia_carga_origen_m": "locations.origin.carry_distance_m",
    "distancia_carga_destino_m": "locations.destination.carry_distance_m",
}


def legacy_result(case):
    fields = extract_lead_data(case["message"])
    state = copy.deepcopy(case["state"])
    changed = {}
    for key, path in LEGACY_MAP.items():
        if key in fields and fields[key] is not None:
            _set(state, path, fields[key])
            changed[path] = fields[key]
    return state, changed, []


def _apply_v2(state, delta):
    changed = {}
    lead_map = {
        "service": "service", "load": "load", "staff_required": "staff.required",
        "packing": "additional_services.packing",
        "packing_required": "additional_services.packing_required",
        "packing_mode": "additional_services.packing",
        "disassembly_required": "additional_services.disassembly_required",
        "assembly_required": "additional_services.assembly_required",
    }
    for key, proposal in delta.changes.lead:
        if proposal is not None:
            path = lead_map[key]
            _set(state, path, proposal.value)
            changed[path] = proposal.value
    for location in delta.changes.locations:
        refs = ["origin", "destination"] if location.ref == "both" else [location.ref]
        for ref in refs:
            for key, proposal in location.set:
                if proposal is not None:
                    path = f"locations.{ref}.{key}"
                    _set(state, path, proposal.value)
                    changed[path] = proposal.value
    return state, changed


def delta_result(case):
    snapshot = CanonicalSnapshot(state_version=f"dataset:{case['id']}", state=case["state"])
    context = DeltaContext(
        payload={
            "state_version": snapshot.state_version,
            "state": snapshot.state,
            "last_bot_question": case.get("last_bot_question"),
            "customer_message": case["message"],
            "recent_turns": case.get("recent_turns", []),
        },
        last_bot_question=case.get("last_bot_question", ""),
        recent_turn_count=len(case.get("recent_turns", [])),
    )
    delta, metrics = extract_conversation_delta(context, provider_name="openai")
    validation = validate_delta_v2(
        delta, snapshot, customer_message=case["message"],
        last_bot_question=case.get("last_bot_question", ""),
        expected_state_version=snapshot.state_version,
    )
    raw_state, raw_changed = _apply_v2(copy.deepcopy(case["state"]), delta)
    accepted_state, accepted_changed = _apply_v2(copy.deepcopy(case["state"]), validation.accepted)
    raw_ambiguities = [item.field for item in delta.ambiguities]
    accepted_ambiguities = [item.field for item in validation.accepted.ambiguities]
    return {
        "raw_state": raw_state, "raw_changed": raw_changed,
        "raw_ambiguities": raw_ambiguities, "delta": delta,
        "accepted_state": accepted_state, "accepted_changed": accepted_changed,
        "accepted_ambiguities": accepted_ambiguities, "validation": validation,
        "metrics": metrics,
    }


def score(case, state, changed, ambiguities, corrections=None):
    tp = fp = fn = 0
    errors = []
    expected = case.get("expected", {})
    for path, value in expected.items():
        actual = _get(state, path)
        if _matches(actual, value):
            tp += 1
        else:
            fn += 1
            errors.append(f"missing_or_wrong:{path}")
    for path, value in case.get("forbidden", {}).items():
        if _matches(_get(state, path), value):
            fp += 1
            errors.append(f"unsafe:{path}")
    expected_paths = set(expected)
    for path, value in changed.items():
        if path not in expected_paths and _get(case["state"], path) != value:
            fp += 1
            errors.append(f"overinference:{path}")
    expected_ambiguities = case.get("expected_ambiguities", [])
    ambiguity_ok = all(any(_norm(term) in _norm(item) for item in ambiguities) for term in expected_ambiguities)
    if expected_ambiguities and not ambiguity_ok:
        fn += len(expected_ambiguities)
        errors.append("ambiguity_missing")
    correction_ok = not case.get("expected_correction") or bool(corrections)
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "correct": not errors and correction_ok,
        "semantic_safe": fp == 0,
        "ambiguity_ok": ambiguity_ok,
        "errors": errors + ([] if correction_ok else ["correction_missing"]),
    }


def aggregate(details):
    tp = sum(item["score"]["tp"] for item in details)
    fp = sum(item["score"]["fp"] for item in details)
    fn = sum(item["score"]["fn"] for item in details)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {
        "correct_cases": sum(item["score"]["correct"] for item in details),
        "safe_cases": sum(item["score"]["semantic_safe"] for item in details),
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
    }


def expand_cases(dataset):
    templates = dataset.get("state_templates", {})
    cases = copy.deepcopy(dataset.get("cases", []))
    for case in cases:
        if "state" not in case and case.get("state_ref") in templates:
            case["state"] = copy.deepcopy(templates[case.pop("state_ref")])
    return cases


class Command(BaseCommand):
    help = "Compara extractor legacy determinístico contra ConversationDelta shadow."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
        parser.add_argument("--validate-only", action="store_true")
        parser.add_argument("--confirm-real-api", action="store_true")
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options):
        dataset = json.loads(options["dataset"].read_text(encoding="utf-8"))
        cases = expand_cases(dataset)
        if not isinstance(cases, list) or not cases or len({case.get("id") for case in cases}) != len(cases):
            raise CommandError("Dataset inválido o IDs duplicados.")
        if options["validate_only"]:
            self.stdout.write(self.style.SUCCESS(f"Dataset delta válido: {len(cases)} casos. Cero APIs."))
            return
        if not options["confirm_real_api"]:
            raise CommandError("Use --confirm-real-api para autorizar OpenAI real.")
        legacy = []
        raw_ai = []
        accepted_ai = []
        usage = []
        for case in cases:
            legacy_state, legacy_changed, legacy_ambiguities = legacy_result(case)
            legacy.append({"id": case["id"], "changed": legacy_changed,
                           "score": score(case, legacy_state, legacy_changed, legacy_ambiguities, [])})
            try:
                result = delta_result(case)
                metrics = result["metrics"]
                usage.append((metrics.input_tokens or 0, metrics.output_tokens or 0, metrics.latency_ms))
                raw_ai.append({"id": case["id"], "changed": result["raw_changed"],
                               "ambiguities": result["raw_ambiguities"],
                               "delta": result["delta"].model_dump(mode="json", exclude_none=True),
                               "schema_valid": True,
                               "score": score(case, result["raw_state"], result["raw_changed"],
                                              result["raw_ambiguities"], result["delta"].corrections)})
                accepted_ai.append({"id": case["id"], "changed": result["accepted_changed"],
                                    "ambiguities": result["accepted_ambiguities"],
                                    "rejected": [{"path": item.path, "reason": item.reason}
                                                 for item in result["validation"].rejected],
                                    "validator_latency_ms": result["validation"].latency_ms,
                                    "score": score(case, result["accepted_state"], result["accepted_changed"],
                                                   result["accepted_ambiguities"],
                                                   result["validation"].accepted.corrections)})
            except Exception as exc:
                failed = {"id": case["id"], "changed": {}, "ambiguities": [], "schema_valid": False,
                          "error_type": type(exc).__name__,
                          "score": {"tp": 0, "fp": 0, "fn": len(case.get("expected", {})),
                                    "correct": False, "semantic_safe": True, "ambiguity_ok": False,
                                    "errors": ["api_or_schema_error"]}}
                raw_ai.append(failed)
                accepted_ai.append(copy.deepcopy(failed))
        latencies = sorted(value for _, _, value in usage if value is not None)
        p95 = latencies[max(0, min(len(latencies) - 1, round(len(latencies) * .95 + .5) - 1))] if latencies else None
        input_tokens = sum(item[0] for item in usage)
        output_tokens = sum(item[1] for item in usage)
        configured_input_rate = settings.OPENAI_INPUT_USD_PER_MILLION
        configured_output_rate = settings.OPENAI_OUTPUT_USD_PER_MILLION
        input_rate = configured_input_rate or GPT41_MINI_INPUT_USD_PER_MILLION
        output_rate = configured_output_rate or GPT41_MINI_OUTPUT_USD_PER_MILLION
        cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
        report = {
            "dataset_version": dataset["version"], "total_cases": len(cases),
            "legacy_scope": "deterministic extract_lead_data; no legacy OpenAI calls",
            "legacy": {"metrics": aggregate(legacy), "cases": legacy},
            "raw_model": {"metrics": aggregate(raw_ai), "cases": raw_ai},
            "accepted_delta": {"metrics": aggregate(accepted_ai), "cases": accepted_ai},
            "usage": {
                "requests": len(usage), "input_tokens": input_tokens, "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "average_latency_ms": round(statistics.mean(latencies), 2) if latencies else None,
                "median_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
                "p95_latency_ms": round(p95, 2) if p95 else None,
                "max_latency_ms": round(max(latencies), 2) if latencies else None,
                "estimated_cost_usd": round(cost, 8),
                "estimated_cost_per_1000_inbounds_usd": round(cost / len(usage) * 1000, 6) if usage else None,
                "input_usd_per_million": input_rate,
                "output_usd_per_million": output_rate,
                "rates_source": "settings" if configured_input_rate and configured_output_rate else "gpt-4.1-mini official fallback",
                "validator_average_latency_ms": round(statistics.mean(
                    item.get("validator_latency_ms", 0) for item in accepted_ai
                ), 4),
            },
        }
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if options["output"]:
            options["output"].write_text(rendered + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Reporte guardado: {options['output']}"))
        else:
            self.stdout.write(rendered)
