from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import override_settings
from django.utils import timezone

from apps.integrations.enums import GenerationStatus, OutboxStatus, Provider
from apps.integrations.models import BotGeneration, IntegrationOutboxEvent
from apps.integrations.services.bot_runtime import authorize_inbound_trigger
from apps.integrations.services.chatwoot_outbox import process_chatwoot_inbound_event
from apps.integrations.services.generations import fail_generation, finalize_generation
from apps.integrations.services.live_sync import canonical_incoming_message
from apps.integrations.tests.base import IntegrationTestCase


class P0InboundResilienceTests(IntegrationTestCase):
    def event(self):
        return {
            "message_id": "wamid-p0-1",
            "text": "Mudanza de Surco a Miraflores",
        }

    def persist(self):
        return canonical_incoming_message(
            lead=self.lead, channel=self.channel, event=self.event(),
            conversation=self.conversation,
        )

    def test_canonical_inbound_always_has_one_durable_chatwoot_event(self):
        first, created, _ = self.persist()
        second, redelivered, _ = self.persist()
        self.assertTrue(created)
        self.assertFalse(redelivered)
        self.assertEqual(first.id, second.id)
        events = IntegrationOutboxEvent.objects.filter(
            destination=Provider.CHATWOOT,
            event_type="sync_inbound_message",
        )
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().safe_payload, {"message_ids": [first.id]})

    def test_failed_generation_is_reclaimed_and_meta_outbox_is_unique(self):
        message, _, _ = self.persist()
        first = authorize_inbound_trigger(message.id)
        self.assertTrue(first.authorized)
        fail_generation(first.generation.id, RuntimeError("secret payload"))
        first.generation.refresh_from_db()
        self.assertEqual(first.generation.status, GenerationStatus.FAILED)
        self.assertEqual(first.generation.error_summary, "RuntimeError")
        self.assertNotIn("secret", first.generation.error_summary)

        retry = authorize_inbound_trigger(message.id)
        self.assertTrue(retry.authorized)
        self.assertEqual(retry.generation.id, first.generation.id)
        _generation, _outbox, published = finalize_generation(
            retry.generation.id, result_text="Respuesta segura"
        )
        self.assertTrue(published)
        duplicate = authorize_inbound_trigger(message.id)
        self.assertFalse(duplicate.authorized)
        self.assertEqual(BotGeneration.objects.count(), 1)
        self.assertEqual(
            IntegrationOutboxEvent.objects.filter(destination=Provider.META_WHATSAPP).count(), 1
        )

    @override_settings(BOT_GENERATION_LEASE_SECONDS=60)
    def test_abandoned_generation_is_reclaimed(self):
        message, _, _ = self.persist()
        first = authorize_inbound_trigger(message.id)
        BotGeneration.objects.filter(pk=first.generation.id).update(
            started_at=timezone.now() - timedelta(minutes=2)
        )
        retry = authorize_inbound_trigger(message.id)
        self.assertTrue(retry.authorized)
        self.assertEqual(retry.generation.id, first.generation.id)
        immediate_duplicate = authorize_inbound_trigger(message.id)
        self.assertFalse(immediate_duplicate.authorized)

    def test_chatwoot_failure_retries_without_touching_meta_outbox(self):
        self.persist()
        event = IntegrationOutboxEvent.objects.get(event_type="sync_inbound_message")
        with patch(
            "apps.integrations.services.chatwoot_outbox.sync_chatwoot_conversation",
            side_effect=TimeoutError("remote body must not persist"),
        ):
            self.assertEqual(process_chatwoot_inbound_event(event.id), "retry")
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.RETRY)
        self.assertEqual(event.error_summary, "TimeoutError")
        self.assertEqual(
            IntegrationOutboxEvent.objects.filter(destination=Provider.META_WHATSAPP).count(), 0
        )

        projection = Mock(messages_failed=0)
        with patch(
            "apps.integrations.services.chatwoot_outbox.sync_chatwoot_conversation",
            return_value=projection,
        ) as sync:
            self.assertEqual(process_chatwoot_inbound_event(event.id), "sent")
            self.assertEqual(process_chatwoot_inbound_event(event.id), "already_sent")
        self.assertEqual(sync.call_count, 1)
