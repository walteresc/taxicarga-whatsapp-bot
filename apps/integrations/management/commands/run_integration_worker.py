import logging
import signal
import socket
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from apps.integrations.enums import OutboxStatus, Provider
from apps.integrations.models import IntegrationOutboxEvent, WorkerHeartbeat
from apps.integrations.services.commercial_labels import process_commercial_label_event
from apps.integrations.services.conversation_data import process_conversation_data_event
from apps.integrations.services.chatwoot_outbox import process_chatwoot_inbound_event
from apps.integrations.services.inbox_outbox import recover_inbox_locks, recover_outbox_locks
from apps.integrations.services.meta_sender import process_meta_outbox_event

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the permanent TaxiCarga integration worker."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=2.0)
        parser.add_argument("--batch-size", type=int, default=20)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--worker-id", default=f"{socket.gethostname()}-integration")

    def handle(self, *args, **options):
        self.stopping = False
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_args: setattr(self, "stopping", True))
        while not self.stopping:
            self.run_once(options)
            if options["once"]:
                break
            time.sleep(max(0.1, options["interval"]))

    def run_once(self, options):
        close_old_connections()
        now = timezone.now()
        worker_id = options["worker_id"]
        WorkerHeartbeat.objects.update_or_create(
            name="integration", defaults={"worker_id": worker_id, "last_seen_at": now, "metadata": {"status": "running"}}
        )
        stale_before = now - timedelta(minutes=10)
        recover_inbox_locks(stale_before)
        recover_outbox_locks(stale_before)
        events = IntegrationOutboxEvent.objects.filter(
            status__in=[OutboxStatus.PENDING, OutboxStatus.RETRY], available_at__lte=now
        ).order_by("available_at", "created_at")[:max(1, options["batch_size"])]
        for event in list(events):
            if self.stopping:
                break
            try:
                if event.destination == Provider.META_WHATSAPP:
                    process_meta_outbox_event(event.id, worker_id=worker_id)
                elif event.destination == Provider.CHATWOOT and event.event_type == "sync_commercial_labels":
                    process_commercial_label_event(event.id)
                elif event.destination == Provider.CHATWOOT and event.event_type == "sync_conversation_data":
                    process_conversation_data_event(event.id)
                elif event.destination == Provider.CHATWOOT and event.event_type == "sync_inbound_message":
                    process_chatwoot_inbound_event(event.id)
            except Exception:
                logger.exception("event_processing_failed event_id=%s", event.id)
        close_old_connections()
