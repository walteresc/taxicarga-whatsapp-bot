from unittest.mock import Mock

from django.db import IntegrityError, transaction
from django.test import override_settings

from apps.integrations.enums import AuthorType, OutboxStatus, OwnerState, Provider, SyncStatus, Visibility
from apps.integrations.errors import PendingHumanOutbox
from apps.integrations.models import (
    BotGeneration,
    ChannelInboxMapping,
    ChatwootAccountMapping,
    ChatwootContactMapping,
    ContactInboxMapping,
    ConversationMapping,
    IntegrationMessage,
    IntegrationOutboxEvent,
)
from apps.integrations.providers.chatwoot.exceptions import ChatwootConnectionError
from apps.integrations.providers.chatwoot.webhook import process_webhook
from apps.integrations.services.attention_control import apply_chatwoot_return_request
from apps.integrations.services.bot_context import build_bot_context
from apps.integrations.services.bot_runtime import authorize_inbound_trigger
from apps.integrations.services.state_machine import return_to_bot, take_conversation
from apps.integrations.tests.base import IntegrationTestCase
from apps.whatsapp.models import MensajeWhatsApp


@override_settings(
    CHATWOOT_ACCOUNT_ID="7",
    CHATWOOT_INBOX_ID="9",
    CHATWOOT_RETURN_TO_BOT_ENABLED=True,
)
class Stage8ReturnTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        account = ChatwootAccountMapping.objects.create(
            environment="stage8", account_id="7", active=True, sync_status=SyncStatus.SYNCED
        )
        inbox = ChannelInboxMapping.objects.create(
            channel=self.channel, account=account, inbox_id="9", inbox_identifier="stage8",
            active=True, sync_status=SyncStatus.SYNCED,
        )
        contact = ChatwootContactMapping.objects.create(
            cliente=self.client_record, account=account, contact_id="11", active=True,
            sync_status=SyncStatus.SYNCED,
        )
        source = ContactInboxMapping.objects.create(
            contact=contact, inbox=inbox, source_id="stage8-source", sync_status=SyncStatus.SYNCED
        )
        self.mapping = ConversationMapping.objects.create(
            conversation=self.conversation, contact_inbox=source,
            external_conversation_id="13", active=True, sync_status=SyncStatus.SYNCED,
        )
        take_conversation(self.conversation.id, actor=self.user, idempotency_key="stage8-take")
        self.conversation.refresh_from_db()
        self.conversation.estado_atencion = self.conversation.ATENCION_ASESOR
        self.conversation.bot_pausado = True
        self.conversation.save(update_fields=["estado_atencion", "bot_pausado"])
        self.lead.atencion_humana = True
        self.lead.bot_pausado = True
        self.lead.save(update_fields=["atencion_humana", "bot_pausado"])

    def conversation_updated(self, value="Bot", previous="Asesor", *, performer=False):
        return {
            "event": "conversation_updated",
            "id": 13,
            "inbox_id": 9,
            "account": {"id": 7},
            "custom_attributes": {"taxicarga_attention_control": value},
            "changed_attributes": [{
                "custom_attributes": {
                    "previous_value": {"taxicarga_attention_control": previous},
                    "current_value": {"taxicarga_attention_control": value},
                }
            }],
            **({"performer": {"id": 3, "type": "user"}} if performer else {}),
        }

    def test_return_is_direct_single_version_and_has_no_bot_work(self):
        self.control.refresh_from_db()
        before = self.control.control_version
        control, audit, changed = return_to_bot(
            self.conversation.id, actor=self.user, idempotency_key="return-once"
        )
        self.assertTrue(changed)
        self.assertEqual(control.owner_state, OwnerState.BOT_ACTIVE)
        self.assertEqual(control.control_version, before + 1)
        self.assertIsNotNone(control.returned_at)
        self.conversation.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertEqual(self.conversation.estado_atencion, self.conversation.ATENCION_BOT)
        self.assertFalse(self.conversation.bot_pausado)
        self.assertFalse(self.lead.atencion_humana)
        self.assertFalse(self.lead.bot_pausado)
        self.assertEqual(BotGeneration.objects.count(), 0)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(destination=Provider.META_WHATSAPP).count(), 0)
        self.assertEqual(audit.version_after, audit.version_before + 1)

    def test_conversation_updated_replay_transitions_once_and_mirror_noops(self):
        client = Mock()
        first = process_webhook(self.conversation_updated(), "stage8-delivery", chatwoot_client=client)
        second = process_webhook(self.conversation_updated(), "stage8-delivery", chatwoot_client=client)
        self.control.refresh_from_db()
        self.assertEqual(first.action, "returned_to_bot")
        self.assertTrue(second.duplicate)
        self.assertEqual(self.control.control_version, 2)
        self.assertEqual(client.update_conversation_custom_attributes.call_count, 1)

        audit = self.conversation.integration_audits.get(action="return_to_bot")
        self.assertEqual(audit.actor_type, "chatwoot_agent")
        self.assertEqual(audit.external_actor_ref, "")
        self.assertEqual(audit.source, "chatwoot_webhook")

        mirror = process_webhook(self.conversation_updated(), "stage8-mirror", chatwoot_client=client)
        self.assertEqual(mirror.action, "ignored")
        self.assertEqual(client.update_conversation_custom_attributes.call_count, 1)

    def test_bot_value_without_explicit_agent_to_bot_change_is_ignored(self):
        cases = [
            {**self.conversation_updated(), "changed_attributes": []},
            {**self.conversation_updated(), "changed_attributes": [{"status": {
                "previous_value": "open", "current_value": "resolved",
            }}]},
            self.conversation_updated(previous="Bot"),
        ]
        for index, payload in enumerate(cases):
            result = process_webhook(payload, f"stage8-no-change-{index}", chatwoot_client=Mock())
            self.assertEqual(result.action, "ignored")
        self.control.refresh_from_db()
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(self.control.control_version, 1)

    def test_root_payload_scope_failures_and_unmapped_are_safe(self):
        wrong_account = self.conversation_updated()
        wrong_account["account"] = {"id": 99}
        wrong_inbox = self.conversation_updated()
        wrong_inbox["inbox_id"] = 99
        unmapped = self.conversation_updated()
        unmapped["id"] = 999
        for index, payload in enumerate((wrong_account, wrong_inbox, unmapped)):
            result = process_webhook(payload, f"stage8-scope-{index}", chatwoot_client=Mock())
            self.assertEqual(result.action, "ignored")
        self.control.refresh_from_db()
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)

    def test_pending_human_outbox_blocks_return_and_reflects_agent(self):
        message = IntegrationMessage.objects.create(
            conversation=self.conversation, provider=Provider.CHATWOOT, external_scope="7",
            direction="outbound", author_type=AuthorType.AGENT, visibility=Visibility.PUBLIC,
            text="pendiente", idempotency_key="stage8-pending-human",
        )
        IntegrationOutboxEvent.objects.create(
            destination=Provider.META_WHATSAPP, destination_scope=str(self.channel.id),
            event_type="send_public_message", logical_message=message,
            idempotency_key="stage8-pending-human", conversation=self.conversation,
            status=OutboxStatus.PENDING,
        )
        client = Mock()
        result = process_webhook(self.conversation_updated(), "stage8-blocked", chatwoot_client=client)
        self.control.refresh_from_db()
        self.conversation.refresh_from_db()
        self.assertEqual(result.action, "return_blocked_pending_human_outbox")
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(self.conversation.estado_atencion, self.conversation.ATENCION_ASESOR)
        self.assertTrue(self.conversation.bot_pausado)
        client.update_conversation_custom_attributes.assert_called_once_with(
            "13", {"taxicarga_attention_control": "Asesor"}
        )

    def test_terminal_human_outbox_does_not_block_and_cancelled_bot_stays_cancelled(self):
        human = IntegrationMessage.objects.create(
            conversation=self.conversation, provider=Provider.CHATWOOT, external_scope="7",
            direction="outbound", author_type=AuthorType.AGENT, visibility=Visibility.PUBLIC,
            text="terminal", idempotency_key="terminal-human",
        )
        IntegrationOutboxEvent.objects.create(
            destination=Provider.META_WHATSAPP, destination_scope=str(self.channel.id), event_type="send",
            logical_message=human, idempotency_key="terminal-human", conversation=self.conversation,
            status=OutboxStatus.SENT,
        )
        bot = IntegrationMessage.objects.create(
            conversation=self.conversation, provider=Provider.INTERNAL, external_scope="internal",
            direction="outbound", author_type=AuthorType.BOT, visibility=Visibility.PUBLIC,
            text="old bot", idempotency_key="old-bot",
        )
        old = IntegrationOutboxEvent.objects.create(
            destination=Provider.META_WHATSAPP, destination_scope=str(self.channel.id), event_type="send",
            logical_message=bot, idempotency_key="old-bot", conversation=self.conversation,
            status=OutboxStatus.CANCELLED,
        )
        return_to_bot(self.conversation.id, actor=self.user, idempotency_key="terminal-return")
        old.refresh_from_db()
        self.assertEqual(old.status, OutboxStatus.CANCELLED)

    def test_reflection_failure_does_not_rollback_django(self):
        client = Mock()
        client.update_conversation_custom_attributes.side_effect = ChatwootConnectionError("offline")
        _control, result = apply_chatwoot_return_request(
            mapping=self.mapping, payload=self.conversation_updated(), account_id="7", inbox_id="9",
            delivery_id="reflection-failure", client=client,
        )
        self.control.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertFalse(result.reflected)
        self.assertEqual(self.control.owner_state, OwnerState.BOT_ACTIVE)

    def test_context_keeps_authors_same_text_and_excludes_system_private(self):
        rows = [
            ("cliente", "A", "wamid-a"),
            ("bot", "igual", "wamid-b"),
            ("asesor", "igual", "wamid-c"),
            ("sistema", "NO INCLUIR", "wamid-d"),
            ("cliente", "E", "wamid-e"),
        ]
        created = []
        for origin, text, provider_id in rows:
            created.append(MensajeWhatsApp.objects.create(
                conversacion=self.conversation, meta_message_id=provider_id,
                direccion="entrante" if origin == "cliente" else "saliente",
                origen=origin, contenido=text, tipo="texto", estado="recibido",
            ))
        IntegrationMessage.objects.create(
            conversation=self.conversation, provider=Provider.CHATWOOT, external_scope="7",
            external_message_id="private-note", direction="internal", author_type=AuthorType.AGENT,
            visibility=Visibility.PRIVATE, text="NOTA PRIVADA", idempotency_key="private-note",
        )
        context = build_bot_context(self.conversation.id, trigger_message_id=created[-1].id)
        rendered = context.as_openai_messages()[0]["content"]
        self.assertIn("Cliente: A", rendered)
        self.assertIn("Bot: igual", rendered)
        self.assertIn("Asesor humano: igual", rendered)
        self.assertIn("Cliente: E", rendered)
        self.assertNotIn("NO INCLUIR", rendered)
        self.assertNotIn("NOTA PRIVADA", rendered)
        self.assertEqual(context.trigger_message_id, created[-1].id)

    def test_provider_identity_is_unique_and_equal_text_with_distinct_ids_remains(self):
        first = MensajeWhatsApp.objects.create(
            conversacion=self.conversation, meta_message_id="wamid-same-provider",
            direccion="entrante", origen="cliente", contenido="igual",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MensajeWhatsApp.objects.create(
                    conversacion=self.conversation, meta_message_id="wamid-same-provider",
                    direccion="entrante", origen="cliente", contenido="igual",
                )
        second = MensajeWhatsApp.objects.create(
            conversacion=self.conversation, meta_message_id="wamid-other-provider",
            direccion="entrante", origen="cliente", contenido="igual",
        )
        context = build_bot_context(self.conversation.id, trigger_message_id=second.id)
        self.assertEqual([entry.message_id for entry in context.entries], [first.id, second.id])

    def test_human_mode_message_is_context_not_pending_trigger(self):
        during_human = MensajeWhatsApp.objects.create(
            conversacion=self.conversation, meta_message_id="wamid-during-human",
            direccion="entrante", origen="cliente", contenido="durante humano",
        )
        denied = authorize_inbound_trigger(during_human.id)
        self.assertFalse(denied.authorized)
        self.assertEqual(BotGeneration.objects.count(), 0)

        return_to_bot(self.conversation.id, actor=self.user, idempotency_key="return-frontier")
        self.assertEqual(BotGeneration.objects.count(), 0)
        new_message = MensajeWhatsApp.objects.create(
            conversacion=self.conversation, meta_message_id="wamid-after-return",
            direccion="entrante", origen="cliente", contenido="nuevo trigger",
        )
        allowed = authorize_inbound_trigger(new_message.id)
        self.assertTrue(allowed.authorized)
        self.assertEqual(allowed.generation.input_message.text, "nuevo trigger")
        self.assertEqual(BotGeneration.objects.count(), 1)
        context = build_bot_context(self.conversation.id, trigger_message_id=new_message.id)
        self.assertEqual(context.trigger_message_id, new_message.id)
        self.assertIn("durante humano", [entry.text for entry in context.entries])

    @override_settings(
        CHATWOOT_HUMAN_TAKEOVER_ENABLED=True,
        CHATWOOT_AGENT_TO_WHATSAPP_ENABLED=False,
    )
    def test_public_human_message_after_return_takes_over_again(self):
        return_to_bot(self.conversation.id, actor=self.user, idempotency_key="return-before-human")
        payload = {
            "event": "message_created", "id": 99, "content": "intervención posterior",
            "message_type": "outgoing", "private": False,
            "sender": {"id": 3, "type": "User"}, "account": {"id": 7},
            "inbox": {"id": 9}, "conversation": {"id": 13},
        }
        result = process_webhook(payload, "human-after-return", chatwoot_client=Mock())
        self.control.refresh_from_db()
        self.assertEqual(result.classification, "human_agent")
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(self.control.control_version, 3)
