from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.integrations.enums import OutboxStatus, Provider
from apps.integrations.models import IntegrationOutboxEvent
from apps.integrations.services.meta_sender import process_meta_outbox_event


class Command(BaseCommand):
    help = "Process scoped Meta outbox events without holding DB locks during HTTP."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--worker-id", default="meta-sender-command")

    def handle(self, *args, **options):
        event_ids = list(
            IntegrationOutboxEvent.objects.filter(
                destination=Provider.META_WHATSAPP,
                status__in=[OutboxStatus.PENDING, OutboxStatus.RETRY],
                available_at__lte=timezone.now(),
            ).order_by("available_at", "created_at").values_list("id", flat=True)[:max(1, options["limit"])]
        )
        sent = 0
        for event_id in event_ids:
            result = process_meta_outbox_event(event_id, worker_id=options["worker_id"])
            sent += result.sent
        self.stdout.write(f"META OUTBOX processed={len(event_ids)} sent={sent}")
