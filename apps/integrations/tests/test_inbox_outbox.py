from datetime import timedelta

from django.utils import timezone

from apps.integrations.enums import InboxStatus, OutboxStatus, Provider
from apps.integrations.errors import IdempotencyConflict
from apps.integrations.errors import PrivateMessageBlocked
from apps.integrations.models import IntegrationMessage
from apps.integrations.services.inbox_outbox import (
    claim_inbox_event,
    claim_outbox_event,
    create_outbox_event,
    fail_inbox,
    fail_outbox,
    mark_inbox_processed,
    mark_outbox_sent,
    recover_inbox_locks,
    recover_outbox_locks,
    register_inbox_event,
    requeue_dead_letter,
    requeue_inbox_dead_letter,
)

from .base import IntegrationTestCase


class InboxOutboxTests(IntegrationTestCase):
    def test_inbox_duplicate_and_hash_conflict(self):
        first, created = register_inbox_event(
            provider=Provider.META_WHATSAPP, event_type="message", idempotency_key="event-1", safe_payload={"safe": 1}
        )
        duplicate, created_again = register_inbox_event(
            provider=Provider.META_WHATSAPP, event_type="message", idempotency_key="event-1", safe_payload={"safe": 1}
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.id, duplicate.id)
        with self.assertRaises(IdempotencyConflict):
            register_inbox_event(
                provider=Provider.META_WHATSAPP, event_type="message", idempotency_key="event-1", safe_payload={"safe": 2}
            )

    def test_inbox_external_id_deduplicates_across_internal_routes(self):
        first, _ = register_inbox_event(
            provider=Provider.META_WHATSAPP, external_scope="phone-1", external_event_id="wamid-1",
            event_type="route-a", idempotency_key="route-a", safe_payload={"safe": 1},
        )
        second, created = register_inbox_event(
            provider=Provider.META_WHATSAPP, external_scope="phone-1", external_event_id="wamid-1",
            event_type="route-b", idempotency_key="route-b", safe_payload={"safe": 1},
        )
        self.assertFalse(created)
        self.assertEqual(first.id, second.id)

    def test_inbox_claim_retry_dead_letter_and_recover(self):
        event, _ = register_inbox_event(
            provider=Provider.INTERNAL, event_type="test", idempotency_key="event", safe_payload={}
        )
        self.assertIsNotNone(claim_inbox_event(event.id, "worker"))
        event.locked_at = timezone.now() - timedelta(minutes=10)
        event.save(update_fields=["locked_at"])
        self.assertEqual(recover_inbox_locks(timezone.now() - timedelta(minutes=5)), 1)
        fail_inbox(event.id, code="temporary", summary="safe")
        event.refresh_from_db()
        self.assertEqual(event.status, InboxStatus.RETRY)
        fail_inbox(event.id, code="permanent", summary="safe", permanent=True)
        event.refresh_from_db()
        self.assertEqual(event.status, InboxStatus.DEAD_LETTER)
        self.assertEqual(requeue_inbox_dead_letter(event.id), 1)

    def test_outbox_lifecycle_has_no_network(self):
        event, created = create_outbox_event(
            destination=Provider.CHATWOOT, event_type="test", idempotency_key="out-1",
            conversation=self.conversation, safe_payload={"safe": True},
        )
        duplicate, created_again = create_outbox_event(
            destination=Provider.CHATWOOT, event_type="test", idempotency_key="out-1",
            conversation=self.conversation, safe_payload={"safe": True},
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(event.id, duplicate.id)
        self.assertIsNotNone(claim_outbox_event(event.id, "worker"))
        mark_outbox_sent(event.id, external_id="simulated")
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.SENT)

    def test_generic_outbox_boundary_blocks_private_meta_message(self):
        message = IntegrationMessage.objects.create(
            conversation=self.conversation, provider=Provider.CHATWOOT,
            direction="internal", author_type="agent", visibility="private", idempotency_key="private",
        )
        with self.assertRaises(PrivateMessageBlocked):
            create_outbox_event(
                destination=Provider.META_WHATSAPP, destination_scope="phone",
                event_type="send", idempotency_key="private-send",
                conversation=self.conversation, logical_message=message,
            )

    def test_outbox_retry_dead_letter_requeue_and_lock_recovery(self):
        event, _ = create_outbox_event(
            destination=Provider.CHATWOOT, event_type="test", idempotency_key="out-1",
            conversation=self.conversation, safe_payload={},
        )
        claim_outbox_event(event.id, "worker")
        event.locked_at = timezone.now() - timedelta(minutes=10)
        event.save(update_fields=["locked_at"])
        self.assertEqual(recover_outbox_locks(timezone.now() - timedelta(minutes=5)), 1)
        fail_outbox(event.id, code="temporary", summary="safe")
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.RETRY)
        fail_outbox(event.id, code="permanent", summary="safe", permanent=True)
        self.assertEqual(requeue_dead_letter(event.id), 1)
