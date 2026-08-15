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
from apps.integrations.services.chatwoot_outbox import process_chatwoot_message_event
from apps.integrations.services.inbox_outbox import recover_inbox_locks, recover_outbox_locks
from apps.integrations.services.meta_sender import process_meta_outbox_event
from apps.ia.delta_extractor import DELTA_SHADOW_EVENT, process_delta_shadow_event
from apps.integrations.services.bot_generation_worker import (
    BOT_GENERATION_EVENT,process_bot_generation_event,
)

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
            # Keep processing while work is available; only sleep when queue is empty
            work_found = self.run_once(options)
            if options["once"]:
                break
            if not work_found:
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

        work_found = len(events) > 0
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
                elif event.destination == Provider.CHATWOOT and event.event_type in {
                    "sync_inbound_message", "sync_outbound_message",
                }:
                    process_chatwoot_message_event(event.id)
                elif event.destination == Provider.INTERNAL and event.event_type == DELTA_SHADOW_EVENT:
                    process_delta_shadow_event(event.id, worker_id=worker_id)
                elif event.destination == Provider.INTERNAL and event.event_type == BOT_GENERATION_EVENT:
                    process_bot_generation_event(event.id,worker_id=worker_id)
            except Exception as worker_exc:
                logger.exception("event_processing_failed event_id=%s error=%s", event.id, type(worker_exc).__name__)
                try:
                    IntegrationOutboxEvent.objects.filter(pk=event.id, status="sending").update(
                        status=OutboxStatus.RETRY, error_summary=str(worker_exc)[:255], locked_at=None, locked_by="")
                except Exception:
                    logger.exception("failed_to_mark_event_retry event_id=%s", event.id)
        close_old_connections()
        return work_found
