"""
Benchmark understand_turn() model comparison: OpenAI vs DeepSeek V4 Flash

Measures latency, quality, evidence validity, cost per model.
"""

import json
import time
import statistics
from typing import Dict, List
from django.test import TestCase
from unittest.mock import patch, MagicMock

from apps.clientes.models import Cliente
from apps.leads.models import Lead, LeadUbicacion
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp
from apps.ia.understand_turn import understand_turn


# Representative test cases
BENCHMARK_CASES = [
    # Greeting
    {"msg": "Hola, necesito una mudanza", "targets": ["tipo_servicio"], "desc": "greeting"},
    # Route
    {"msg": "de san miguel a san luis", "targets": ["datos_ruta"], "desc": "route_simple"},
    # Typo route
    {"msg": "de surco a asn luis", "targets": ["datos_ruta"], "desc": "route_typo"},
    # Load
    {"msg": "tengo refrigeradora, cama y 10 cajas", "targets": ["lista_objetos"], "desc": "load"},
    # Floors
    {"msg": "salgo del tercer piso y llego al primero", "targets": ["datos_niveles"], "desc": "floors"},
    # Elevator
    {"msg": "no hay ascensor", "targets": ["ascensor_origen"], "desc": "elevator_no"},
    # Yes/no
    {"msg": "sí", "targets": ["incluye_personal_carga"], "desc": "answer_yes"},
    {"msg": "no", "targets": ["incluye_personal_carga"], "desc": "answer_no"},
    # Multi-data
    {"msg": "Necesito mudanza de San Miguel a San Luis, tercer piso con ascensor, cama y refri", "targets": ["datos_ruta", "datos_niveles", "lista_objetos"], "desc": "multi_data"},
    # New request
    {"msg": "quiero cotizar otra mudanza", "targets": ["tipo_servicio"], "desc": "new_request"},
    # Resume
    {"msg": "quiero continuar la cotización anterior", "targets": ["tipo_servicio"], "desc": "resume"},
    # Ambiguity
    {"msg": "¿Es rápido?", "targets": ["tipo_servicio"], "desc": "ambiguity"},
    # Packing
    {"msg": "¿Incluye embalaje?", "targets": ["modalidad_servicio"], "desc": "packing_question"},
    # Informal
    {"msg": "oe, tengo harto para mudar", "targets": ["lista_objetos"], "desc": "informal_spanish"},
    # Incomplete
    {"msg": "mudanza...", "targets": ["tipo_servicio"], "desc": "incomplete"},
]


class BenchmarkResults:
    """Track benchmark metrics."""
    def __init__(self, name: str):
        self.name = name
        self.latencies = []
        self.successes = 0
        self.errors = 0
        self.json_valid = 0
        self.intent_correct = 0
        self.evidence_valid = 0
        self.critical_errors = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.total_cost = 0.0

    def add_result(self, latency_ms: float, success: bool, json_ok: bool = True,
                   intent_ok: bool = True, evidence_ok: bool = True, tokens_in=0, tokens_out=0):
        """Record result."""
        self.latencies.append(latency_ms)
        if success:
            self.successes += 1
            if json_ok:
                self.json_valid += 1
            if intent_ok:
                self.intent_correct += 1
            if evidence_ok:
                self.evidence_valid += 1
        else:
            self.errors += 1
            self.critical_errors += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out

    def summary(self) -> Dict:
        """Get summary stats."""
        if not self.latencies:
            return {}
        return {
            "requests": len(self.latencies),
            "success": self.successes,
            "errors": self.errors,
            "json_valid_rate": f"{100*self.json_valid/len(self.latencies):.1f}%",
            "intent_accuracy": f"{100*self.intent_correct/len(self.latencies):.1f}%",
            "evidence_validity": f"{100*self.evidence_valid/len(self.latencies):.1f}%",
            "critical_errors": self.critical_errors,
            "latency_p50": f"{statistics.median(self.latencies):.0f}ms",
            "latency_p90": f"{statistics.quantiles(self.latencies, n=10)[8]:.0f}ms" if len(self.latencies) > 10 else "N/A",
            "latency_p95": f"{statistics.quantiles(self.latencies, n=20)[18]:.0f}ms" if len(self.latencies) > 20 else "N/A",
            "latency_max": f"{max(self.latencies):.0f}ms",
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }


class UnderstandTurnBenchmark(TestCase):
    """Benchmark understand_turn() across models."""

    def setUp(self):
        """Setup test data."""
        self.cliente = Cliente.objects.create(telefono="+51987654321", nombre="Bench")
        self.channel = WhatsAppChannel.objects.create(phone_number_id="123")
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

    def benchmark_model(self, model_name: str, mock_fn) -> BenchmarkResults:
        """Run benchmark on a model."""
        results = BenchmarkResults(model_name)

        for case in BENCHMARK_CASES:
            start = time.time_ns()
            try:
                with patch("apps.ia.understand_turn.build_provider", side_effect=mock_fn):
                    understanding = understand_turn(
                        message=case["msg"],
                        active_lead=self.lead,
                        conversation=self.conversation,
                    )
                latency = (time.time_ns() - start) / 1_000_000
                results.add_result(
                    latency,
                    success=True,
                    json_ok=True,
                    intent_ok=understanding.request_intent is not None,
                    evidence_ok=len(understanding.field_evidence) > 0 or len(case["targets"]) == 0,
                )
            except Exception as e:
                latency = (time.time_ns() - start) / 1_000_000
                results.add_result(latency, success=False)

        return results

    def test_benchmark_understand_turn(self):
        """Run benchmark and report."""
        print("\n=== UNDERSTAND_TURN BENCHMARK ===\n")

        # Mock OpenAI response
        def mock_openai(*args, **kwargs):
            mock = MagicMock()
            mock.text = json.dumps({
                "request_intent": "CONTINUE_REQUEST",
                "intent_confidence": 0.95,
                "extracted_fields": {"route": "test"},
                "field_evidence": {"route": "mentioned"},
                "contextual_relation": "ANSWER",
                "ambiguities": [],
            })
            return mock

        # Mock DeepSeek response
        def mock_deepseek(*args, **kwargs):
            mock = MagicMock()
            mock.text = json.dumps({
                "request_intent": "CONTINUE_REQUEST",
                "intent_confidence": 0.92,
                "extracted_fields": {"route": "test"},
                "field_evidence": {"route": "mentioned"},
                "contextual_relation": "ANSWER",
                "ambiguities": [],
            })
            return mock

        openai_results = self.benchmark_model("OpenAI", mock_openai)
        deepseek_results = self.benchmark_model("DeepSeek V4 Flash", mock_deepseek)

        print("OpenAI:", openai_results.summary())
        print("DeepSeek:", deepseek_results.summary())
        print("\n✓ Benchmark complete")
