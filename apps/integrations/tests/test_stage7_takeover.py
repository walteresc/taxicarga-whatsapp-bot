from unittest.mock import Mock, patch

from django.test import override_settings

from apps.integrations.enums import AuthorType, OutboxStatus, OwnerState, Provider, SyncStatus
from apps.integrations.models import (
    BotGeneration,
    ChannelInboxMapping,
    ChatwootAccountMapping,
    ChatwootContactMapping,
    ContactInboxMapping,
    ConversationMapping,
    ConversationTransitionAudit,
    IntegrationMessage,
    IntegrationOutboxEvent,
)
from apps.integrations.services.human_takeover import apply_chatwoot_human_takeover
from apps.integrations.services.meta_sender import process_meta_outbox_event
from apps.integrations.tests.base import IntegrationTestCase


@override_settings(
    CHATWOOT_HUMAN_TAKEOVER_ENABLED=True,
    CHATWOOT_AGENT_TO_WHATSAPP_ENABLED=True,
    META_OUTBOX_ENABLED=True,
)
class Stage7TakeoverTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.scope = override_settings(CHATWOOT_STAGE7_TEST_CHANNEL_ID=str(self.channel.id))
        self.scope.enable()
        account = ChatwootAccountMapping.objects.create(
            environment="test", account_id="7", active=True, sync_status=SyncStatus.SYNCED
        )
        inbox = ChannelInboxMapping.objects.create(
            channel=self.channel, account=account, inbox_id="9", inbox_identifier="test",
            active=True, sync_status=SyncStatus.SYNCED,
        )
        contact = ChatwootContactMapping.objects.create(
            cliente=self.client_record, account=account, contact_id="11",
            active=True, sync_status=SyncStatus.SYNCED,
        )
        contact_inbox = ContactInboxMapping.objects.create(
            contact=contact, inbox=inbox, source_id="source", sync_status=SyncStatus.SYNCED
        )
        self.mapping = ConversationMapping.objects.create(
            conversation=self.conversation, contact_inbox=contact_inbox,
            external_conversation_id="13", active=True, sync_status=SyncStatus.SYNCED,
        )

    def tearDown(self):
        self.scope.disable()
        super().tearDown()

    def takeover(self, message_id="17", content="TEST TAKEOVER ETAPA 7"):
        return apply_chatwoot_human_takeover(
            mapping_id=self.mapping.id,
            payload={"content": content, "sender": {"id": 3}},
            account_id="7", inbox_id="9", message_id=message_id,
        )

    def test_takeover_is_idempotent_and_second_message_is_distinct(self):
        first = self.takeover()
        replay = self.takeover()
        second = self.takeover("18", "second")
        self.control.refresh_from_db()
        self.conversation.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertTrue(first.transitioned)
        self.assertFalse(replay.transitioned)
        self.assertFalse(second.transitioned)
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(self.control.control_version, 1)
        self.assertTrue(self.conversation.bot_pausado)
        self.assertTrue(self.lead.bot_pausado)
        self.assertEqual(ConversationTransitionAudit.objects.count(), 1)
        self.assertEqual(IntegrationMessage.objects.count(), 2)
        self.assertEqual(IntegrationOutboxEvent.objects.count(), 2)

    def test_takeover_cancels_generation_and_pending_bot_outbox(self):
        bot_message = IntegrationMessage.objects.create(
            conversation=self.conversation, provider=Provider.INTERNAL,
            external_scope="test", direction="outbound", author_type=AuthorType.BOT,
            visibility="public", text="late", idempotency_key="late",
        )
        generation = BotGeneration.objects.create(
            conversation=self.conversation, control_version_started=0,
            status="generating", request_key="generation",
        )
        bot_outbox = IntegrationOutboxEvent.objects.create(
            destination=Provider.META_WHATSAPP, destination_scope=str(self.channel.id),
            event_type="send", logical_message=bot_message, idempotency_key="bot-pending",
            conversation=self.conversation,
        )
        self.takeover()
        generation.refresh_from_db()
        bot_outbox.refresh_from_db()
        self.assertEqual(generation.status, "cancelled")
        self.assertEqual(bot_outbox.status, OutboxStatus.CANCELLED)

    def test_sender_persists_meta_id_and_replay_does_not_send(self):
        outbox = self.takeover().outbox
        sender = Mock(return_value={"messages": [{"id": "wamid.stage7"}]})
        first = process_meta_outbox_event(outbox.id, sender=sender)
        replay = process_meta_outbox_event(outbox.id, sender=sender)
        outbox.refresh_from_db()
        self.assertTrue(first.sent)
        self.assertFalse(replay.sent)
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(outbox.external_id, "wamid.stage7")

    def test_ambiguous_timeout_reuses_same_outbox(self):
        outbox = self.takeover().outbox
        result = process_meta_outbox_event(
            outbox.id, sender=Mock(side_effect=TimeoutError("uncertain"))
        )
        outbox.refresh_from_db()
        self.assertEqual(result.status, OutboxStatus.RETRY)
        self.assertEqual(IntegrationOutboxEvent.objects.count(), 1)
        self.assertEqual(outbox.error_code, "ambiguous_meta_result")

    def test_physical_gate_blocks_bot_after_takeover_but_allows_agent(self):
        self.takeover()
        with patch("apps.whatsapp.services.requests.post") as post:
            from apps.whatsapp.services import send_whatsapp_message
            blocked = send_whatsapp_message(
                self.client_record.telefono, "bot", self.channel,
                author_type=AuthorType.BOT, conversation_id=self.conversation.id,
            )
        self.assertEqual(blocked["reason"], "ownership_gate")
        post.assert_not_called()
