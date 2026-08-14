"""
Baseline latency benchmark para pipeline IA actual.
Ejecuta 9 casos de conversación y mide:
- LLM call count
- Latencia por call
- Latencia total del turno
"""

import logging
import time
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import datetime

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import WhatsAppChannel
from apps.ia.conversation_engine import handle_incoming_message

logger = logging.getLogger(__name__)


class LLMCallTracker:
    """Rastrear todas las llamadas LLM durante ejecución."""

    def __init__(self):
        self.calls = []
        self.current_turn = None

    def start_turn(self, case_name):
        self.current_turn = {
            "case": case_name,
            "llm_calls": [],
            "start_time": time.time(),
        }

    def end_turn(self):
        if self.current_turn:
            self.current_turn["end_time"] = time.time()
            self.current_turn["total_ms"] = (self.current_turn["end_time"] - self.current_turn["start_time"]) * 1000
            self.calls.append(self.current_turn)
            self.current_turn = None

    def track_llm_call(self, func_name, duration_ms):
        if self.current_turn:
            self.current_turn["llm_calls"].append({
                "func": func_name,
                "duration_ms": duration_ms,
            })

    def summary(self):
        """Generar resumen de latencia."""
        total_calls = sum(len(turn["llm_calls"]) for turn in self.calls)
        total_ms = sum(turn["total_ms"] for turn in self.calls)

        summary = {
            "total_turns": len(self.calls),
            "total_llm_calls": total_calls,
            "avg_calls_per_turn": total_calls / len(self.calls) if self.calls else 0,
            "total_ms": total_ms,
            "avg_ms_per_turn": total_ms / len(self.calls) if self.calls else 0,
            "turns": self.calls,
        }
        return summary


tracker = LLMCallTracker()


def mock_generate_ai_result(messages, system_prompt=None, *, responsibility="conversation", provider_name=None, _original=None):
    """Mock que rastrea tiempo de llamadas LLM."""
    start = time.time()
    result = _original(messages, system_prompt, responsibility=responsibility, provider_name=provider_name)
    duration = (time.time() - start) * 1000
    tracker.track_llm_call(f"generate_ai_result[{responsibility}]", duration)
    return result


@override_settings(
    OPENAI_API_KEY="sk-test-key",
    OPENAI_MODEL="gpt-4.1-mini",
    DEBUG=True,
)
class BaselineLatencyBenchmark(TestCase):
    """Benchmark de latencia baseline del pipeline IA actual."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        """Preparar cliente y lead."""
        self.cliente = Cliente.objects.create(
            telefono="+51987654321",
            nombre="Test Cliente",
        )
        self.channel = WhatsAppChannel.objects.create(
            phone_number_id="123456789",
            numero_celular="+51987654321",
        )
        self.lead = Lead.objects.create(
            cliente=self.cliente,
            whatsapp_channel=self.channel,
            tipo_servicio=Lead.MUDANZA,
            etapa_conversacion=Lead.ETAPA_INICIO,
        )

    def run_case(self, case_name, message, expected_contains=None):
        """Ejecutar un caso de benchmark."""
        tracker.start_turn(case_name)
        try:
            reply = handle_incoming_message(
                self.cliente,
                message,
                generation_id=None,
                lead=self.lead,
            )
            tracker.end_turn()

            if expected_contains and expected_contains not in reply:
                logger.warning(f"Case {case_name}: no coincide contenido esperado")

            return reply
        except Exception as e:
            tracker.end_turn()
            logger.error(f"Case {case_name}: error {e}")
            raise

    @patch("apps.ia.openai_client.generate_ai_result")
    def test_01_first_message(self, mock_llm):
        """Caso 1: Primer mensaje."""
        mock_llm.side_effect = lambda *args, **kwargs: MagicMock(text="¿Qué necesitas trasladar?")
        self.run_case("01_first_message", "Hola, necesito una mudanza")

    @patch("apps.ia.openai_client.generate_ai_result")
    def test_02_contextual_route(self, mock_llm):
        """Caso 2: Ruta contextual."""
        self.lead.tipo_servicio = Lead.MUDANZA
        self.lead.save()
        mock_llm.side_effect = lambda *args, **kwargs: MagicMock(text="¿Qué cosas llevarías?")
        self.run_case("02_contextual_route", "de san miguel a san luis")

    @patch("apps.ia.openai_client.generate_ai_result")
    def test_03_load(self, mock_llm):
        """Caso 3: Carga."""
        mock_llm.side_effect = lambda *args, **kwargs: MagicMock(text="¿De qué piso?")
        self.run_case("03_load", "tengo refrigeradora, cama y 10 cajas")

    @patch("apps.ia.openai_client.generate_ai_result")
    def test_04_floors(self, mock_llm):
        """Caso 4: Pisos."""
        mock_llm.side_effect = lambda *args, **kwargs: MagicMock(text="¿Hay ascensor?")
        self.run_case("04_floors", "salgo del tercer piso y llego al primero")

    @patch("apps.ia.openai_client.generate_ai_result")
    def test_05_elevator(self, mock_llm):
        """Caso 5: Ascensor."""
        mock_llm.side_effect = lambda *args, **kwargs: MagicMock(text="Perfecto")
        self.run_case("05_elevator", "no hay ascensor")

    @patch("apps.ia.openai_client.generate_ai_result")
    def test_06_multi_data(self, mock_llm):
        """Caso 6: Multi-data."""
        mock_llm.side_effect = lambda *args, **kwargs: MagicMock(text="Gracias")
        self.run_case(
            "06_multi_data",
            "Necesito una mudanza de San Miguel a San Luis, salgo del tercer piso con ascensor y llevo cama, refrigeradora y 10 cajas."
        )

    @patch("apps.ia.openai_client.generate_ai_result")
    def test_07_new_request(self, mock_llm):
        """Caso 7: Nueva solicitud."""
        mock_llm.side_effect = lambda *args, **kwargs: MagicMock(text="Nueva cotización iniciada")
        self.run_case("07_new_request", "quiero cotizar otra mudanza")

    @patch("apps.ia.openai_client.generate_ai_result")
    def test_08_resume(self, mock_llm):
        """Caso 8: Resumir cotización."""
        mock_llm.side_effect = lambda *args, **kwargs: MagicMock(text="Continuando")
        self.run_case("08_resume", "quiero continuar la cotización anterior")

    @patch("apps.ia.openai_client.generate_ai_result")
    def test_09_complex_packing(self, mock_llm):
        """Caso 9: Pregunta compleja de embalaje."""
        mock_llm.side_effect = lambda *args, **kwargs: MagicMock(text="Sí, incluye embalaje")
        self.run_case(
            "09_complex_packing",
            "¿El precio incluye embalaje? También salgo de un tercer piso."
        )

    def print_summary(self):
        """Imprimir resumen de benchmark."""
        summary = tracker.summary()
        logger.info(f"\n=== BASELINE LATENCY BENCHMARK ===")
        logger.info(f"Total turns: {summary['total_turns']}")
        logger.info(f"Total LLM calls: {summary['total_llm_calls']}")
        logger.info(f"Avg calls/turn: {summary['avg_calls_per_turn']:.2f}")
        logger.info(f"Total ms: {summary['total_ms']:.0f}")
        logger.info(f"Avg ms/turn: {summary['avg_ms_per_turn']:.0f}")

        for turn in summary['turns']:
            logger.info(f"\n{turn['case']}: {turn['total_ms']:.0f}ms ({len(turn['llm_calls'])} LLM calls)")
            for call in turn['llm_calls']:
                logger.info(f"  - {call['func']}: {call['duration_ms']:.0f}ms")
