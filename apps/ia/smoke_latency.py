"""
Smoke test: Measure end-to-end latency of bot generation pipeline (5 cases, local, no Meta).

Usage:
  python manage.py shell < apps/ia/smoke_latency.py
"""
import os
import sys
import django
import time
from statistics import mean, stdev

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel
from apps.integrations.models import ConversationControl, BotGeneration
from apps.ia.request_lifecycle import resolve_request_lifecycle
from apps.ia.latency_telemetry import GenerationTelemetry

print("=" * 70)
print("LATENCY SMOKE TEST — LOCAL PIPELINE")
print("=" * 70)
print()

# Setup
client = Cliente.objects.create(telefono="51900000smoke")
channel = WhatsAppChannel.objects.create(nombre="SMOKE TEST", phone_number_id="smoke123")

cases = [
    {
        "name": "Clean request (null lead)",
        "setup": lambda conv: None,  # leave lead as null
        "message": "Hola, necesito una mudanza",
    },
    {
        "name": "Active lead continuation",
        "setup": lambda conv: Lead.objects.create(
            cliente=conv.cliente,
            whatsapp_channel=conv.channel,
            estado=Lead.DATOS_INCOMPLETOS
        ),
        "message": "Sí, continuemos",
    },
    {
        "name": "Active lead ambiguous",
        "setup": lambda conv: Lead.objects.create(
            cliente=conv.cliente,
            whatsapp_channel=conv.channel,
            estado=Lead.DATOS_INCOMPLETOS
        ),
        "message": "Necesito cotizar un servicio",
    },
]

latencies = []

for i, case in enumerate(cases[:3], 1):  # Run first 3 for smoke test
    conv = ConversacionWhatsApp.objects.create(
        cliente=client,
        channel=channel
    )
    ConversationControl.objects.create(conversation=conv)

    # Setup lead
    lead = case["setup"](conv)
    if lead:
        conv.lead = lead
        conv.save()

    # Measure
    print(f"Case {i}: {case['name']}")
    gen_id = f"smoke{i}"
    telemetry = GenerationTelemetry(gen_id)
    start = time.time()
    try:
        result_lead, reply, intent = resolve_request_lifecycle(
            conversation_id=conv.id,
            message=case["message"],
            generation_id=gen_id,
            telemetry=telemetry
        )
        elapsed_ms = (time.time() - start) * 1000
        latencies.append(elapsed_ms)
        summary = telemetry.get_summary()
        openai_calls = [k for k in summary["steps"].keys() if k.startswith("openai_")]
        print(f"  ✓ {elapsed_ms:.0f}ms | Intent: {intent.value}")
        print(f"    OpenAI calls: {', '.join(openai_calls) if openai_calls else 'none'}")
        if openai_calls:
            for call_key in openai_calls:
                calls = summary["steps"][call_key]["calls"]
                for j, call in enumerate(calls, 1):
                    print(f"      {call_key} #{j}: {call['duration_ms']:.0f}ms, retries={call['retries']}, tokens={call['input_tokens']}/{call['output_tokens']}")
    except Exception as e:
        print(f"  ✗ Error: {type(e).__name__}: {str(e)[:60]}")
    print()

# Summary
if latencies:
    print("=" * 70)
    print("LATENCY SUMMARY")
    print("=" * 70)
    print(f"Average: {mean(latencies):.0f}ms")
    print(f"Min:     {min(latencies):.0f}ms")
    print(f"Max:     {max(latencies):.0f}ms")
    if len(latencies) > 1:
        print(f"StdDev:  {stdev(latencies):.0f}ms")
    print()
    if max(latencies) > 20000:
        print("⚠ WARNING: Latency > 20s detected. Check OpenAI timeout configuration.")
    print()
