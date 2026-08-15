"""
Measure real latency from database timestamps.
Query actual events and calculate queue/api/total times.
"""

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from apps.integrations.models import BotGeneration, IntegrationOutboxEvent
from apps.integrations.enums import Provider, OutboxStatus
import statistics


class Command(BaseCommand):
    help = "Measure real latency from database events"

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=1, help="Look back N hours")
        parser.add_argument("--limit", type=int, default=100, help="Max events to analyze")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=options["hours"])

        print("\n" + "="*70)
        print("REAL LATENCY MEASUREMENT")
        print("="*70 + "\n")

        # Find BotGenerations from last N hours
        generations = BotGeneration.objects.filter(
            started_at__gte=cutoff
        ).order_by("-started_at")[:options["limit"]]

        print(f"Analyzing {generations.count()} BotGenerations...")

        gen_data = []
        for gen in generations:
            # Get the first outbox event for this generation
            outbox = IntegrationOutboxEvent.objects.filter(
                conversation_id=gen.conversation_id,
                destination=Provider.META_WHATSAPP,
                created_at__gte=gen.started_at
            ).order_by("created_at").first()

            if not outbox:
                continue

            # Calculate times (ms)
            gen_complete = gen.completed_at or timezone.now()

            # Queue wait: when was this generation's outbox event first processed?
            queue_wait_ms = None
            if outbox.locked_at and outbox.created_at:
                queue_wait_ms = (outbox.locked_at - outbox.created_at).total_seconds() * 1000

            # Generation time (understand_turn + django)
            gen_time_ms = (gen_complete - gen.started_at).total_seconds() * 1000

            # Meta send time
            meta_send_ms = None
            if outbox.sent_at and outbox.locked_at:
                meta_send_ms = (outbox.sent_at - outbox.locked_at).total_seconds() * 1000

            # Server total: generation start to outbox sent
            server_total_ms = None
            if outbox.sent_at:
                server_total_ms = (outbox.sent_at - gen.started_at).total_seconds() * 1000

            gen_data.append({
                'gen_id': str(gen.id)[:8],
                'gen_time_ms': gen_time_ms,
                'queue_wait_ms': queue_wait_ms or 0,
                'meta_send_ms': meta_send_ms or 0,
                'server_total_ms': server_total_ms or 0,
            })

        if not gen_data:
            print("No completed events found.")
            return

        print(f"\n{len(gen_data)} events measured.\n")

        # Calculate aggregates
        gen_times = [d['gen_time_ms'] for d in gen_data if d['gen_time_ms'] > 0]
        queue_waits = [d['queue_wait_ms'] for d in gen_data if d['queue_wait_ms'] > 0]
        meta_sends = [d['meta_send_ms'] for d in gen_data if d['meta_send_ms'] > 0]
        server_totals = [d['server_total_ms'] for d in gen_data if d['server_total_ms'] > 0]

        def print_stats(label, data):
            if not data:
                print(f"{label}: N/A")
                return
            print(f"{label}:")
            print(f"  mean: {statistics.mean(data):.0f} ms")
            print(f"  p50:  {statistics.median(data):.0f} ms")
            if len(data) > 10:
                p90 = statistics.quantiles(data, n=10)[8]
                p95 = statistics.quantiles(data, n=20)[18]
                print(f"  p90:  {p90:.0f} ms")
                print(f"  p95:  {p95:.0f} ms")
            print(f"  max:  {max(data):.0f} ms")

        print_stats("GENERATION TIME (understand_turn + Django)", gen_times)
        print()
        print_stats("QUEUE WAIT (created to claimed)", queue_waits)
        print()
        print_stats("META SEND (claimed to sent)", meta_sends)
        print()
        print_stats("SERVER TOTAL (gen start to meta sent)", server_totals)

        print("\n" + "="*70 + "\n")
