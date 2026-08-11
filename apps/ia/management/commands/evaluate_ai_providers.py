import json
import re
import statistics
import unicodedata
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ia.openai_client import ExtractionSchemaError, extract_lead_with_ai, generate_ai_result
from apps.ia.prompts import CONVERSATIONAL_RESPONSE_SYSTEM_PROMPT


DATASET_PATH = Path(__file__).resolve().parents[2] / "tests_data" / "ai_ab_dataset.json"


def _normalized(value):
    if isinstance(value, str):
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
        return " ".join(value.split())
    return value


def _matches(actual, expected):
    actual = _normalized(actual)
    expected = _normalized(expected)
    if isinstance(actual, str) and isinstance(expected, str):
        return actual == expected or expected in actual
    return actual == expected


def _lead(values):
    return SimpleNamespace(**values)


def _cost(provider, input_tokens, output_tokens):
    prefix = provider.upper()
    input_rate = getattr(settings, f"{prefix}_INPUT_USD_PER_MILLION")
    output_rate = getattr(settings, f"{prefix}_OUTPUT_USD_PER_MILLION")
    return ((input_tokens or 0) * input_rate + (output_tokens or 0) * output_rate) / 1_000_000


def _operation_metrics(samples, provider):
    input_tokens = sum(item[0] or 0 for item in samples)
    output_tokens = sum(item[1] or 0 for item in samples)
    latencies = sorted(item[2] for item in samples if item[2] is not None)
    p95_index = max(0, min(len(latencies) - 1, round(0.95 * len(latencies) + 0.5) - 1)) if latencies else 0
    cost = _cost(provider, input_tokens, output_tokens)
    return {
        "requests": len(samples),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "average_latency_ms": round(statistics.mean(latencies), 2) if latencies else None,
        "median_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
        "p95_latency_ms": round(latencies[p95_index], 2) if latencies else None,
        "max_latency_ms": round(max(latencies), 2) if latencies else None,
        "estimated_cost_usd": round(cost, 8),
        "estimated_cost_per_case_usd": round(cost / len(samples), 8) if samples else None,
        "estimated_cost_per_1000_turns_usd": round(cost / len(samples) * 1000, 6) if samples else None,
        "rates_are_configurable": True,
    }


class Command(BaseCommand):
    help = "Evalúa localmente OpenAI y DeepSeek con dataset TEST anonimizado."

    def add_arguments(self, parser):
        parser.add_argument("--provider", choices=["openai", "deepseek", "both"], default="both")
        parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
        parser.add_argument("--validate-only", action="store_true")
        parser.add_argument("--confirm-real-api", action="store_true")
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options):
        dataset = json.loads(options["dataset"].read_text(encoding="utf-8"))
        self._validate(dataset)
        if options["validate_only"]:
            self.stdout.write(self.style.SUCCESS(
                f"Dataset válido: {len(dataset['extraction'])} extracción, "
                f"{len(dataset['conversation'])} conversación. Cero llamadas API."
            ))
            return
        if not options["confirm_real_api"]:
            raise CommandError("Use --confirm-real-api para autorizar consumo real.")

        providers = ["openai", "deepseek"] if options["provider"] == "both" else [options["provider"]]
        report = {"dataset_version": dataset["version"], "providers": {}}
        for provider in providers:
            report["providers"][provider] = self._evaluate(provider, dataset)

        rendered = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        if options["output"]:
            options["output"].write_text(rendered + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Reporte guardado: {options['output']}"))
        else:
            self.stdout.write(rendered)

    def _validate(self, dataset):
        if not isinstance(dataset.get("extraction"), list) or not isinstance(dataset.get("conversation"), list):
            raise CommandError("Dataset requiere listas extraction y conversation.")
        ids = [case.get("id") for group in ("extraction", "conversation") for case in dataset[group]]
        if not all(ids) or len(ids) != len(set(ids)):
            raise CommandError("Cada caso requiere id único.")

    def _evaluate(self, provider, dataset):
        extraction = self._evaluate_extraction(provider, dataset["extraction"])
        conversation = self._evaluate_conversation(provider, dataset["conversation"])
        extraction_samples = extraction.pop("usage_samples")
        conversation_samples = conversation.pop("usage_samples")
        totals = [*extraction_samples, *conversation_samples]
        return {
            "extraction": extraction,
            "conversation": conversation,
            "operation": _operation_metrics(totals, provider),
            "operation_by_task": {
                "extraction": _operation_metrics(extraction_samples, provider),
                "conversation": _operation_metrics(conversation_samples, provider),
            },
        }

    def _evaluate_extraction(self, provider, cases):
        tp = fp = fn = schema_failures = api_errors = 0
        usage = []
        details = []
        field_metrics = {}
        for case in cases:
            try:
                result = extract_lead_with_ai(
                    case["message"],
                    _lead(case.get("lead", {})),
                    case.get("history"),
                    provider_name=provider,
                    raise_errors=True,
                )
            except ExtractionSchemaError:
                schema_failures += 1
                details.append({"id": case["id"], "status": "schema_failure"})
                continue
            except Exception:
                api_errors += 1
                details.append({"id": case["id"], "status": "api_error"})
                continue
            fields = result.get("campos_detectados")
            if not isinstance(fields, dict):
                schema_failures += 1
                details.append({"id": case["id"], "status": "schema_failure"})
                continue
            metrics = result.get("metrics", {})
            usage.append((metrics.get("input_tokens"), metrics.get("output_tokens"), metrics.get("latency_ms")))
            case_errors = []
            for field, expected in case.get("expected", {}).items():
                metric = field_metrics.setdefault(field, {"tp": 0, "fp": 0, "fn": 0})
                if field not in fields:
                    fn += 1
                    metric["fn"] += 1
                    case_errors.append(f"missing:{field}")
                elif _matches(fields[field], expected):
                    tp += 1
                    metric["tp"] += 1
                else:
                    fp += 1
                    fn += 1
                    metric["fp"] += 1
                    metric["fn"] += 1
                    case_errors.append(f"wrong:{field}")
            for field, forbidden in case.get("forbidden", {}).items():
                if field in fields and _matches(fields[field], forbidden):
                    fp += 1
                    metric = field_metrics.setdefault(field, {"tp": 0, "fp": 0, "fn": 0})
                    metric["fp"] += 1
                    case_errors.append(f"forbidden:{field}")
            details.append({
                "id": case["id"],
                "status": "ok" if not case_errors else "fail",
                "errors": case_errors,
                "fields": fields,
            })
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        return {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "schema_failures": schema_failures,
            "api_errors": api_errors,
            "field_metrics": field_metrics,
            "cases": details,
            "usage_samples": usage,
        }

    def _evaluate_conversation(self, provider, cases):
        passed = errors = 0
        usage = []
        details = []
        for case in cases:
            prompt = (
                f"Mensaje actual: {case['message']}\n"
                f"Objetivo autorizado por Django: {case['objective']}\n"
                "Redacta respuesta breve sin cambiar objetivo."
            )
            result = generate_ai_result(
                [{"role": "user", "content": prompt}],
                CONVERSATIONAL_RESPONSE_SYSTEM_PROMPT,
                responsibility="conversation",
                provider_name=provider,
            )
            if result is None:
                errors += 1
                details.append({"id": case["id"], "status": "api_error"})
                continue
            usage.append((result.input_tokens, result.output_tokens, result.latency_ms))
            text = result.text
            normalized = _normalized(text)
            failures = []
            sentence_count = len([part for part in re.split(r"[.!?]+", text) if part.strip()])
            if sentence_count > case.get("max_sentences", 3):
                failures.append("not_brief")
            for forbidden in case.get("forbidden", []):
                if _normalized(forbidden) in normalized:
                    failures.append(f"forbidden:{forbidden}")
            required = case.get("required_any", [])
            if required and not any(_normalized(term) in normalized for term in required):
                failures.append("objective_term_missing")
            if failures:
                details.append({"id": case["id"], "status": "fail", "errors": failures, "response": text})
            else:
                passed += 1
                details.append({"id": case["id"], "status": "ok", "response": text})
        return {
            "passed": passed,
            "failed": len(cases) - passed - errors,
            "api_errors": errors,
            "cases": details,
            "usage_samples": usage,
        }
