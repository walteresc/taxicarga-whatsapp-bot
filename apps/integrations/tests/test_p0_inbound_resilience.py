from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import override_settings
from django.utils import timezone

from apps.integrations.enums import AuthorType, GenerationStatus, OutboxStatus, Provider
from apps.integrations.models import BotGeneration, IntegrationMessage, IntegrationOutboxEvent
from apps.integrations.services.bot_runtime import authorize_inbound_trigger
from apps.integrations.services.chatwoot_outbox import (
    process_chatwoot_inbound_event,
    process_chatwoot_message_event,
)
from apps.integrations.services.generations import fail_generation, finalize_generation
from apps.integrations.services.live_sync import canonical_incoming_message
from apps.integrations.services.meta_sender import process_meta_outbox_event
from apps.integrations.tests.base import IntegrationTestCase
from apps.whatsapp.models import MensajeWhatsApp


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

    @override_settings(META_OUTBOX_ENABLED=True, CHATWOOT_LIVE_SYNC_ENABLED=True)
    def test_meta_accepted_outbound_projects_once_after_chatwoot_retry(self):
        logical = IntegrationMessage.objects.create(
            conversation=self.conversation,
            provider=Provider.INTERNAL,
            external_scope="test",
            channel=self.channel,
            direction="outbound",
            author_type=AuthorType.BOT,
            visibility="public",
            text="Respuesta bot",
            idempotency_key="p0-outbound",
        )
        meta_event = IntegrationOutboxEvent.objects.create(
            destination=Provider.META_WHATSAPP,
            destination_scope=str(self.channel.id),
            event_type="send_public_message",
            logical_message=logical,
            idempotency_key="meta-p0-outbound",
            conversation=self.conversation,
            safe_payload={"control_version": self.control.control_version},
        )
        sender = Mock(return_value={"messages": [{"id": "wamid.p0-outbound"}]})

        self.assertTrue(process_meta_outbox_event(meta_event.id, sender=sender).sent)
        outgoing = MensajeWhatsApp.objects.get(meta_message_id="wamid.p0-outbound")
        chatwoot_event = IntegrationOutboxEvent.objects.get(
            destination=Provider.CHATWOOT,
            event_type="sync_outbound_message",
        )
        self.assertEqual(chatwoot_event.safe_payload, {"message_ids": [outgoing.id]})

        with patch(
            "apps.integrations.services.chatwoot_outbox.sync_chatwoot_conversation",
            side_effect=TimeoutError("chatwoot unavailable"),
        ):
            self.assertEqual(process_chatwoot_message_event(chatwoot_event.id), "retry")

        projection = Mock(messages_failed=0)
        with patch(
            "apps.integrations.services.chatwoot_outbox.sync_chatwoot_conversation",
            return_value=projection,
        ) as sync:
            self.assertEqual(process_chatwoot_message_event(chatwoot_event.id), "sent")
            self.assertEqual(process_chatwoot_message_event(chatwoot_event.id), "already_sent")

        replay = process_meta_outbox_event(meta_event.id, sender=sender)
        self.assertFalse(replay.sent)
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(sync.call_count, 1)
        self.assertEqual(
            MensajeWhatsApp.objects.filter(
                direccion=MensajeWhatsApp.SALIENTE,
                contenido="Respuesta bot",
            ).count(),
            1,
        )
        self.assertEqual(
            IntegrationOutboxEvent.objects.filter(
                destination=Provider.CHATWOOT,
                event_type="sync_outbound_message",
            ).count(),
            1,
        )
