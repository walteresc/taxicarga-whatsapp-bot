from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.integrations.models import ChannelIntegrationPolicy, IntegrationInboxEvent, IntegrationOutboxEvent, WorkerHeartbeat


class Command(BaseCommand):
    help = "Show sanitized integration operational status."

    def handle(self, *args, **options):
        heartbeat = WorkerHeartbeat.objects.filter(name="integration").first()
        fresh = bool(heartbeat and heartbeat.last_seen_at >= timezone.now() - timedelta(minutes=2))
        self.stdout.write(f"worker={'healthy' if fresh else 'stale_or_missing'}")
        self.stdout.write(f"inbox_total={IntegrationInboxEvent.objects.count()}")
        self.stdout.write(f"outbox_total={IntegrationOutboxEvent.objects.count()}")
        self.stdout.write(f"enabled_channels={ChannelIntegrationPolicy.objects.filter(enabled=True).count()}")
