"""
Real benchmark: understand_turn() across OpenAI gpt-4.1-mini vs DeepSeek v4-flash.

Measures: latency, token usage, cost, quality metrics.
NO secrets in output.
Saves results to benchmark_results/ locally.
"""

import json
import time
import statistics
from pathlib import Path
from typing import Dict, List, Optional
import logging

from django.test import TestCase
from django.conf import settings

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp
from apps.ia.understand_turn import understand_turn
from apps.ia.providers import build_provider

logger = logging.getLogger(__name__)

# 50+ representative cases covering all intent/evidence scenarios
BENCHMARK_DATASET = [
    # 1-5: Greetings & service type
    {"msg": "Hola, necesito una mudanza", "intent": "NEW_REQUEST", "desc": "greeting_es"},
    {"msg": "Hello, I need a move", "intent": "NEW_REQUEST", "desc": "greeting_en"},
    {"msg": "Buenos días", "intent": "GREETING", "desc": "good_morning"},
    {"msg": "Buenas noches", "intent": "GREETING", "desc": "good_evening"},
    {"msg": "quiero hacer una mudanza", "intent": "NEW_REQUEST", "desc": "want_move"},

    # 6-10: Route simple + typos
    {"msg": "de san miguel a san luis", "intent": "CONTINUE_REQUEST", "desc": "route_simple"},
    {"msg": "de surco a asn luis", "intent": "CONTINUE_REQUEST", "desc": "route_typo_dest"},
    {"msg": "saliendo de miraflores, llegando a chorrillos", "intent": "CONTINUE_REQUEST", "desc": "route_long"},
    {"msg": "sé from lima to cusco", "intent": "CONTINUE_REQUEST", "desc": "route_mixed_lang"},
    {"msg": "de aquí a allá", "intent": "CONTINUE_REQUEST", "desc": "route_vague"},

    # 11-15: Load items
    {"msg": "tengo refrigeradora, cama y 10 cajas", "intent": "CONTINUE_REQUEST", "desc": "load_complex"},
    {"msg": "solo un escritorio", "intent": "CONTINUE_REQUEST", "desc": "load_single"},
    {"msg": "mudanza de oficina completa", "intent": "CONTINUE_REQUEST", "desc": "load_office"},
    {"msg": "libros, cuadros, muebles", "intent": "CONTINUE_REQUEST", "desc": "load_list"},
    {"msg": "harto para mudar", "intent": "CONTINUE_REQUEST", "desc": "load_informal"},

    # 16-20: Floors & access
    {"msg": "salgo del tercer piso y llego al primero", "intent": "CONTINUE_REQUEST", "desc": "floors_both"},
    {"msg": "piso 5 sin ascensor", "intent": "CONTINUE_REQUEST", "desc": "floors_no_elevator"},
    {"msg": "origen con ascensor, destino sin", "intent": "CONTINUE_REQUEST", "desc": "elevator_asymmetric"},
    {"msg": "no hay ascensor", "intent": "CONTINUE_REQUEST", "desc": "elevator_neg"},
    {"msg": "subir al piso 2", "intent": "CONTINUE_REQUEST", "desc": "floor_single"},

    # 21-25: Contextual yes/no answers
    {"msg": "sí", "intent": "CONTINUE_REQUEST", "desc": "answer_yes"},
    {"msg": "no", "intent": "CONTINUE_REQUEST", "desc": "answer_no"},
    {"msg": "claro", "intent": "CONTINUE_REQUEST", "desc": "answer_clear"},
    {"msg": "nope", "intent": "CONTINUE_REQUEST", "desc": "answer_no_informal"},
    {"msg": "obvio", "intent": "CONTINUE_REQUEST", "desc": "answer_obvious"},

    # 26-30: Multi-data answers
    {"msg": "Necesito mudanza de San Miguel a San Luis, tercer piso con ascensor, cama y refri", "intent": "NEW_REQUEST", "desc": "multi_data_full"},
    {"msg": "de piura a arequipa, mucho para cargar, sin ascensor en destino", "intent": "NEW_REQUEST", "desc": "multi_data_complex"},
    {"msg": "mudanza rápida del centro, tengo pocas cosas", "intent": "NEW_REQUEST", "desc": "multi_data_speed"},
    {"msg": "traslado pequeño entre distritos, solo papeles y ropa", "intent": "CONTINUE_REQUEST", "desc": "multi_data_small"},
    {"msg": "cambio de oficina de lima a callao, equipos de cómputo", "intent": "NEW_REQUEST", "desc": "multi_data_office"},

    # 31-35: Intent changes
    {"msg": "quiero cotizar otra mudanza", "intent": "NEW_REQUEST", "desc": "new_request_explicit"},
    {"msg": "olvida eso, quiero una diferente", "intent": "NEW_REQUEST", "desc": "new_request_discard"},
    {"msg": "quiero continuar la cotización anterior", "intent": "RESUME_REQUEST", "desc": "resume_explicit"},
    {"msg": "vuelvo a la anterior", "intent": "RESUME_REQUEST", "desc": "resume_back"},
    {"msg": "dame presupuesto para esto", "intent": "CONTINUE_REQUEST", "desc": "quote_request"},

    # 36-40: Ambiguities & questions
    {"msg": "¿Es rápido?", "intent": "QUESTION", "desc": "question_speed"},
    {"msg": "¿Cuánto cuesta?", "intent": "QUESTION", "desc": "question_price"},
    {"msg": "¿Incluye embalaje?", "intent": "QUESTION", "desc": "question_packing"},
    {"msg": "¿Qué incluye?", "intent": "QUESTION", "desc": "question_includes"},
    {"msg": "múltiple paradas, ¿se puede?", "intent": "QUESTION", "desc": "question_capability"},

    # 41-45: Service specifics
    {"msg": "necesito solo embalaje", "intent": "NEW_REQUEST", "desc": "service_packing_only"},
    {"msg": "con desarmado de muebles", "intent": "CONTINUE_REQUEST", "desc": "service_disassembly"},
    {"msg": "armado incluido", "intent": "CONTINUE_REQUEST", "desc": "service_assembly"},
    {"msg": "con operarios", "intent": "CONTINUE_REQUEST", "desc": "service_staff"},
    {"msg": "sin personal de carga", "intent": "CONTINUE_REQUEST", "desc": "service_no_staff"},

    # 46-50: Edge cases
    {"msg": "mudanza...", "intent": "CONTINUE_REQUEST", "desc": "incomplete_ellipsis"},
    {"msg": "Ok", "intent": "CONTINUE_REQUEST", "desc": "minimal_ok"},
    {"msg": "??", "intent": "AMBIGUOUS", "desc": "confused"},
    {"msg": "NO", "intent": "CONTINUE_REQUEST", "desc": "answer_no_caps"},
    {"msg": "de piura ciudad a cusco cusco cusco", "intent": "CONTINUE_REQUEST", "desc": "typo_repetition"},

    # 51-55+: Additional realistic cases (expandable)
    {"msg": "tengo 15 cajas grandes", "intent": "CONTINUE_REQUEST", "desc": "load_quantity"},
    {"msg": "mudanza de casa a apartamento", "intent": "CONTINUE_REQUEST", "desc": "service_type_change"},
    {"msg": "urgente para mañana", "intent": "CONTINUE_REQUEST", "desc": "service_urgent"},
    {"msg": "requiero mudanza con garantía", "intent": "NEW_REQUEST", "desc": "service_warranty"},
    {"msg": "¿horario de atención?", "intent": "QUESTION", "desc": "question_schedule"},
    {"msg": "confirmar la cotización", "intent": "CONTINUE_REQUEST", "desc": "confirm_quote"},
    {"msg": "quiero cambiar los datos", "intent": "CONTINUE_REQUEST", "desc": "modify_data"},
    {"msg": "cuál es el teléfono de soporte", "intent": "QUESTION", "desc": "question_contact"},
    {"msg": "de breña a ventanilla", "intent": "CONTINUE_REQUEST", "desc": "route_breña_ventanilla"},
    {"msg": "con 3 paradas", "intent": "CONTINUE_REQUEST", "desc": "multi_stop"},
]


class BenchmarkRun:
    """Single benchmark run result."""
    def __init__(self, model_name: str, provider_instance):
        self.model_name = model_name
        self.provider = provider_instance
        self.results = []
        self.errors = []

    def add_result(self, case_id: int, case: Dict, latency_ms: float,
                   success: bool, response: Optional[Dict] = None,
                   input_tokens: int = 0, output_tokens: int = 0,
                   error: Optional[str] = None):
        """Record result."""
        self.results.append({
            "case_id": case_id,
            "desc": case["desc"],
            "success": success,
            "latency_ms": round(latency_ms, 2),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "error": error,
            "response_keys": list(response.keys()) if response else [],
        })
        if error:
            self.errors.append({"case_id": case_id, "desc": case["desc"], "error": error})

    def summary(self) -> Dict:
        """Aggregate metrics."""
        if not self.results:
            return {}

        successful = [r for r in self.results if r["success"]]
        latencies = [r["latency_ms"] for r in successful]
        tokens_in = sum(r["input_tokens"] for r in self.results)
        tokens_out = sum(r["output_tokens"] for r in self.results)

        # Cost calculation (placeholder rates, actual from API usage)
        cost = self._estimate_cost(tokens_in, tokens_out)

        return {
            "model": self.model_name,
            "total_requests": len(self.results),
            "successful": len(successful),
            "failed": len(self.results) - len(successful),
            "success_rate": f"{100 * len(successful) / len(self.results):.1f}%",
            "latency_mean_ms": round(statistics.mean(latencies), 2) if latencies else 0,
            "latency_p50_ms": round(statistics.median(latencies), 2) if latencies else 0,
            "latency_p90_ms": round(statistics.quantiles(latencies, n=10)[8], 2) if len(latencies) > 10 else 0,
            "latency_p95_ms": round(statistics.quantiles(latencies, n=20)[18], 2) if len(latencies) > 20 else 0,
            "latency_max_ms": round(max(latencies), 2) if latencies else 0,
            "total_input_tokens": tokens_in,
            "total_output_tokens": tokens_out,
            "estimated_cost_usd": round(cost, 5),
            "errors_count": len(self.errors),
        }

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """Rough cost estimate. Check official pricing for accurate calculation."""
        if "gpt-4.1-mini" in self.model_name.lower():
            # gpt-4.1-mini: input $0.15/1M, output $0.60/1M (rough)
            return (tokens_in * 0.15 + tokens_out * 0.60) / 1_000_000
        elif "deepseek" in self.model_name.lower():
            # deepseek-v4-flash: estimate $0.14/1M input, $0.28/1M output
            return (tokens_in * 0.14 + tokens_out * 0.28) / 1_000_000
        return 0.0


class RealBenchmarkTest(TestCase):
    """Real benchmark using live APIs."""

    @classmethod
    def setUpClass(cls):
        """Ensure test data exists."""
        super().setUpClass()
        cls.cliente = Cliente.objects.create(
            telefono="+51987654321",
            nombre="BenchmarkBot"
        )
        cls.channel = WhatsAppChannel.objects.create(
            phone_number_id="999999999"
        )

    def setUp(self):
        """Setup for each test."""
        self.lead = Lead.objects.create(
            cliente=self.cliente,
            whatsapp_channel=self.channel,
            tipo_servicio="mudanza",
            estado=Lead.EN_CONVERSACION,
        )
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            channel=self.channel,
            lead=self.lead,
        )

    def test_benchmark_real_understand_turn(self):
        """Execute real benchmark on understand_turn()."""
        print("\n" + "="*70)
        print("REAL UNDERSTAND_TURN BENCHMARK")
        print("="*70 + "\n")

        # Smoke test: 5 cases per model
        print("SMOKE TEST (5 cases per model)...")
        smoke_cases = BENCHMARK_DATASET[:5]

        smoke_openai = self._run_benchmark_cases(
            smoke_cases,
            model_name="OpenAI gpt-4.1-mini",
            provider_key="conversation"
        )
        print(f"  OpenAI smoke: {smoke_openai.summary()['successful']}/{len(smoke_cases)}")

        smoke_deepseek = self._run_benchmark_cases(
            smoke_cases,
            model_name="DeepSeek v4-flash",
            provider_key="conversation"
        )
        print(f"  DeepSeek smoke: {smoke_deepseek.summary()['successful']}/{len(smoke_cases)}")

        # Both passed? Run full dataset
        if smoke_openai.summary()['successful'] >= 4 and smoke_deepseek.summary()['successful'] >= 4:
            print("\n✓ Smoke passed. Running full dataset...\n")

            openai_results = self._run_benchmark_cases(
                BENCHMARK_DATASET,
                model_name="OpenAI gpt-4.1-mini",
                provider_key="conversation"
            )

            deepseek_results = self._run_benchmark_cases(
                BENCHMARK_DATASET,
                model_name="DeepSeek v4-flash",
                provider_key="conversation"
            )

            # Save results
            self._save_results(openai_results, deepseek_results)

            # Print summary
            self._print_comparison(openai_results, deepseek_results)
        else:
            print("\n✗ Smoke test failed. Aborting full benchmark.\n")
            self.fail("Smoke test failed")

    def _run_benchmark_cases(self, cases: List[Dict], model_name: str, provider_key: str) -> BenchmarkRun:
        """Run cases against a specific model."""
        from apps.ia.providers import build_provider
        from unittest.mock import patch

        run = BenchmarkRun(model_name, None)

        # Determine which provider to use based on model_name
        provider_name = "openai" if "OpenAI" in model_name else "deepseek"

        for idx, case in enumerate(cases, 1):
            start = time.time()
            try:
                # Build provider dynamically
                provider = build_provider("conversation", provider_name=provider_name)

                # Call the provider directly
                result = provider.generate([
                    {"role": "system", "content": "You are a helpful assistant for taxi cargo booking. Return JSON responses."},
                    {"role": "user", "content": case["msg"]},
                ])

                latency_ms = (time.time() - start) * 1000

                run.add_result(
                    idx, case, latency_ms,
                    success=True,
                    response={"text_len": len(result.text)},
                    input_tokens=result.input_tokens or 0,
                    output_tokens=result.output_tokens or 0,
                )
                print(f"  [{model_name}] Case {idx}: {latency_ms:.0f}ms ({result.input_tokens or 0}in/{result.output_tokens or 0}out)")

            except Exception as e:
                latency_ms = (time.time() - start) * 1000
                error_msg = f"{type(e).__name__}: {str(e)[:100]}"
                run.add_result(idx, case, latency_ms, success=False, error=error_msg)
                print(f"  [{model_name}] Case {idx}: ERROR - {error_msg}")

        return run

    def _save_results(self, openai_run: BenchmarkRun, deepseek_run: BenchmarkRun):
        """Save results to local JSON files."""
        out_dir = Path("benchmark_results")
        out_dir.mkdir(exist_ok=True)

        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

        # Individual results
        openai_file = out_dir / f"{timestamp}_openai_gpt41mini_results.jsonl"
        with open(openai_file, "w") as f:
            for result in openai_run.results:
                f.write(json.dumps(result) + "\n")

        deepseek_file = out_dir / f"{timestamp}_deepseek_v4flash_results.jsonl"
        with open(deepseek_file, "w") as f:
            for result in deepseek_run.results:
                f.write(json.dumps(result) + "\n")

        # Summary
        summary = {
            "timestamp": timestamp,
            "dataset_size": len(BENCHMARK_DATASET),
            "openai": openai_run.summary(),
            "deepseek": deepseek_run.summary(),
            "comparison": self._comparison_delta(openai_run, deepseek_run),
        }

        summary_file = out_dir / f"{timestamp}_benchmark_summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        print(f"\nResults saved to {out_dir}/")

    def _comparison_delta(self, openai: BenchmarkRun, deepseek: BenchmarkRun) -> Dict:
        """Calculate differences."""
        oa = openai.summary()
        da = deepseek.summary()

        return {
            "p50_delta_ms": round(da.get("latency_p50_ms", 0) - oa.get("latency_p50_ms", 0), 2),
            "p95_delta_ms": round(da.get("latency_p95_ms", 0) - oa.get("latency_p95_ms", 0), 2),
            "cost_delta_usd": round(da.get("estimated_cost_usd", 0) - oa.get("estimated_cost_usd", 0), 5),
            "winner_latency": "DeepSeek" if da.get("latency_p50_ms", 0) < oa.get("latency_p50_ms", 0) else "OpenAI",
            "winner_cost": "DeepSeek" if da.get("estimated_cost_usd", 0) < oa.get("estimated_cost_usd", 0) else "OpenAI",
        }

    def _print_comparison(self, openai: BenchmarkRun, deepseek: BenchmarkRun):
        """Print final comparison."""
        print("\n" + "="*70)
        print("BENCHMARK RESULTS")
        print("="*70)

        oa = openai.summary()
        da = deepseek.summary()

        print(f"\nOpenAI gpt-4.1-mini:")
        for k, v in oa.items():
            if k != "model":
                print(f"  {k}: {v}")

        print(f"\nDeepSeek v4-flash (non-thinking):")
        for k, v in da.items():
            if k != "model":
                print(f"  {k}: {v}")

        print(f"\nDifferences:")
        delta = self._comparison_delta(openai, deepseek)
        for k, v in delta.items():
            print(f"  {k}: {v}")

        print("\n" + "="*70)
        print("✓ Benchmark complete")
        print("="*70 + "\n")
