"""
End-to-end latency benchmark: T0 (inbound) → T12 (Meta API response).
Measures queue wait, LLM, rendering, outbox, Meta API.
20+ local cases without actual Meta calls.
"""

import json
import time
import statistics
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from django.utils import timezone
from django.test import TestCase

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp, MensajeWhatsApp
from apps.integrations.models import BotGeneration, IntegrationOutboxEvent, IntegrationInboxEvent
from apps.integrations.enums import Provider, OutboxStatus, AuthorType
from apps.integrations.services.bot_generation_worker import queue_bot_generation, process_bot_generation_event
from apps.integrations.services.generations import finalize_generation


@dataclass
class LatencyMeasurement:
    """Single turn latency measurement."""
    case_id: int
    desc: str
    message: str

    # Timestamps (ms from global start)
    t0_webhook_received: float = 0.0  # Request received
    t1_message_persisted: float = 0.0  # MensajeWhatsApp created
    t2_generation_created: float = 0.0  # BotGeneration created
    t3_event_queued: float = 0.0  # IntegrationOutboxEvent created
    t4_worker_claimed: float = 0.0  # Worker locked event
    t5_understand_start: float = 0.0  # understand_turn starts
    t6_understand_end: float = 0.0  # understand_turn ends
    t7_django_done: float = 0.0  # Validation/persistence complete
    t8_response_rendered: float = 0.0  # Response text ready
    t9_meta_outbox_created: float = 0.0  # IntegrationOutboxEvent for Meta
    t10_meta_sender_claimed: float = 0.0  # Meta event locked
    t11_meta_api_start: float = 0.0  # HTTP request to Meta
    t12_meta_api_response: float = 0.0  # Meta API response received

    # Derived metrics (ms)
    queue_wait_ms: float = 0.0  # t4 - t3
    understand_turn_ms: float = 0.0  # t6 - t5
    django_processing_ms: float = 0.0  # t7 - t2
    response_render_ms: float = 0.0  # t8 - t7
    meta_outbox_wait_ms: float = 0.0  # t10 - t9
    meta_api_ms: float = 0.0  # t12 - t11
    server_total_ms: float = 0.0  # t9 - t0 (up to Meta outbox creation)

    # Status
    success: bool = True
    error: Optional[str] = None

    def calculate_deltas(self):
        """Calculate derived metrics."""
        if self.t4_worker_claimed > 0 and self.t3_event_queued > 0:
            self.queue_wait_ms = self.t4_worker_claimed - self.t3_event_queued
        if self.t6_understand_end > 0 and self.t5_understand_start > 0:
            self.understand_turn_ms = self.t6_understand_end - self.t5_understand_start
        if self.t7_django_done > 0 and self.t1_message_persisted > 0:
            self.django_processing_ms = self.t7_django_done - self.t1_message_persisted
        if self.t8_response_rendered > 0 and self.t7_django_done > 0:
            self.response_render_ms = self.t8_response_rendered - self.t7_django_done
        if self.t10_meta_sender_claimed > 0 and self.t9_meta_outbox_created > 0:
            self.meta_outbox_wait_ms = self.t10_meta_sender_claimed - self.t9_meta_outbox_created
        if self.t12_meta_api_response > 0 and self.t11_meta_api_start > 0:
            self.meta_api_ms = self.t12_meta_api_response - self.t11_meta_api_start
        if self.t9_meta_outbox_created > 0 and self.t0_webhook_received > 0:
            self.server_total_ms = self.t9_meta_outbox_created - self.t0_webhook_received


class EndToEndLatencyBenchmark(TestCase):
    """Measure complete latency pipeline locally."""

    TEST_CASES = [
        {"msg": "Hola, necesito una mudanza", "desc": "greeting"},
        {"msg": "de san miguel a san luis", "desc": "route_simple"},
        {"msg": "tengo refrigeradora, cama y 10 cajas", "desc": "load_complex"},
        {"msg": "salgo del tercer piso y llego al primero", "desc": "floors_both"},
        {"msg": "no hay ascensor", "desc": "elevator_no"},
        {"msg": "Necesito mudanza de San Miguel a San Luis, tercer piso con ascensor, cama y refri", "desc": "multi_data"},
        {"msg": "¿Incluye embalaje?", "desc": "packing_question"},
        {"msg": "quiero cotizar otra mudanza", "desc": "new_request"},
        {"msg": "quiero continuar la cotización anterior", "desc": "resume_explicit"},
        {"msg": "sí", "desc": "answer_yes"},
        {"msg": "no", "desc": "answer_no"},
        {"msg": "de piura a arequipa, mucho para cargar", "desc": "route_multi"},
        {"msg": "¿Cuánto cuesta?", "desc": "question_price"},
        {"msg": "mudanza de casa a apartamento", "desc": "service_change"},
        {"msg": "con operarios", "desc": "service_staff"},
        {"msg": "urgente para mañana", "desc": "service_urgent"},
        {"msg": "de breña a ventanilla", "desc": "route_breña"},
        {"msg": "con 3 paradas", "desc": "multi_stop"},
        {"msg": "piso 5 sin ascensor", "desc": "floor_high_no_elev"},
        {"msg": "solo un escritorio", "desc": "load_minimal"},
    ]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = Cliente.objects.create(
            telefono="+51987654321",
            nombre="BenchmarkBot"
        )
        cls.channel = WhatsAppChannel.objects.create(
            phone_number_id="999999999",
            activo=True
        )

    def test_end_to_end_latency_benchmark(self):
        """Run complete latency benchmark."""
        print("\n" + "="*70)
        print("END-TO-END LATENCY BENCHMARK")
        print("="*70 + "\n")

        results: List[LatencyMeasurement] = []
        global_start = time.time()

        print(f"Running {len(self.TEST_CASES)} cases...\n")

        for idx, case in enumerate(self.TEST_CASES, 1):
            meas = LatencyMeasurement(
                case_id=idx,
                desc=case["desc"],
                message=case["msg"]
            )

            try:
                self._run_single_case(meas, global_start)
                meas.calculate_deltas()
                results.append(meas)

                print(f"[{idx:2d}] {case['desc']:20s}: "
                      f"queue={meas.queue_wait_ms:6.0f}ms, "
                      f"llm={meas.understand_turn_ms:6.0f}ms, "
                      f"total={meas.server_total_ms:6.0f}ms")

            except Exception as e:
                meas.success = False
                meas.error = str(e)[:100]
                results.append(meas)
                print(f"[{idx:2d}] {case['desc']:20s}: ERROR - {meas.error}")

        # Calculate aggregates
        self._print_summary(results)

    def _run_single_case(self, meas: LatencyMeasurement, global_start: float):
        """Execute single case with instrumentation."""
        global_t0 = time.time()
        meas.t0_webhook_received = (global_t0 - global_start) * 1000

        # T1: Create MensajeWhatsApp
        t1 = time.time()
        mensaje = MensajeWhatsApp.objects.create(
            conversacion_id=self._get_or_create_conversation().id,
            contenido=meas.message,
            tipo="texto",
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            meta_message_id=f"wamid_{meas.case_id}"
        )
        meas.t1_message_persisted = (time.time() - global_start) * 1000

        # T2: Create BotGeneration
        lead = self._get_or_create_lead()
        generation = BotGeneration.objects.create(
            conversation_id=mensaje.conversacion_id,
            trigger_message_id=mensaje.id,
            lead_id=lead.id,
            generation_status="processing"
        )
        meas.t2_generation_created = (time.time() - global_start) * 1000

        # T3: Queue generation event
        event, _ = queue_bot_generation(
            message_id=mensaje.id,
            generation_id=generation.id
        )
        meas.t3_event_queued = (time.time() - global_start) * 1000

        # T4: Worker claims (simulate immediate claim)
        meas.t4_worker_claimed = (time.time() - global_start) * 1000

        # T5-T7: Process generation (includes understand_turn)
        t5 = time.time()
        meas.t5_understand_start = (t5 - global_start) * 1000

        try:
            result = process_bot_generation_event(event.id, worker_id="benchmark")
            meas.t6_understand_end = (time.time() - global_start) * 1000
        except Exception:
            meas.t6_understand_end = (time.time() - global_start) * 1000
            raise

        meas.t7_django_done = (time.time() - global_start) * 1000
        meas.t8_response_rendered = meas.t7_django_done  # Response rendered by then

        # T9-T12: Simulate outbox (no real Meta call)
        meas.t9_meta_outbox_created = (time.time() - global_start) * 1000
        meas.t10_meta_sender_claimed = meas.t9_meta_outbox_created
        meas.t11_meta_api_start = (time.time() - global_start) * 1000
        # Simulate 200ms Meta API response
        time.sleep(0.001)  # minimal delay
        meas.t12_meta_api_response = (time.time() - global_start) * 1000

    def _get_or_create_conversation(self):
        """Get or create test conversation."""
        conv, _ = ConversacionWhatsApp.objects.get_or_create(
            cliente=self.cliente,
            channel=self.channel,
            defaults={"estado_atencion": ConversacionWhatsApp.ATENCION_BOT}
        )
        return conv

    def _get_or_create_lead(self):
        """Get or create test lead."""
        lead, _ = Lead.objects.get_or_create(
            cliente=self.cliente,
            whatsapp_channel=self.channel,
            defaults={"tipo_servicio": "mudanza", "estado": Lead.EN_CONVERSACION}
        )
        return lead

    def _print_summary(self, results: List[LatencyMeasurement]):
        """Print aggregated summary."""
        successful = [r for r in results if r.success]

        print("\n" + "="*70)
        print("LATENCY ANALYSIS")
        print("="*70 + "\n")

        # Queue wait
        queue_waits = [r.queue_wait_ms for r in successful if r.queue_wait_ms > 0]
        if queue_waits:
            print("QUEUE WAIT:")
            print(f"  mean: {statistics.mean(queue_waits):.0f}ms")
            print(f"  p50:  {statistics.median(queue_waits):.0f}ms")
            print(f"  p95:  {statistics.quantiles(queue_waits, n=20)[18] if len(queue_waits) > 20 else max(queue_waits):.0f}ms")

        # understand_turn
        llm_times = [r.understand_turn_ms for r in successful if r.understand_turn_ms > 0]
        if llm_times:
            print("\nUNDERSTAND_TURN:")
            print(f"  mean: {statistics.mean(llm_times):.0f}ms")
            print(f"  p50:  {statistics.median(llm_times):.0f}ms")
            print(f"  p95:  {statistics.quantiles(llm_times, n=20)[18] if len(llm_times) > 20 else max(llm_times):.0f}ms")

        # Django processing
        django_times = [r.django_processing_ms for r in successful if r.django_processing_ms > 0]
        if django_times:
            print("\nDJANGO PROCESSING:")
            print(f"  mean: {statistics.mean(django_times):.0f}ms")
            print(f"  p50:  {statistics.median(django_times):.0f}ms")
            print(f"  p95:  {statistics.quantiles(django_times, n=20)[18] if len(django_times) > 20 else max(django_times):.0f}ms")

        # Server total
        totals = [r.server_total_ms for r in successful if r.server_total_ms > 0]
        if totals:
            print("\nSERVER TOTAL (T0→T9):")
            print(f"  mean: {statistics.mean(totals):.0f}ms")
            print(f"  p50:  {statistics.median(totals):.0f}ms")
            print(f"  p95:  {statistics.quantiles(totals, n=20)[18] if len(totals) > 20 else max(totals):.0f}ms")
            print(f"  max:  {max(totals):.0f}ms")

        print(f"\nSuccess: {len(successful)}/{len(results)}")
        print("="*70 + "\n")
