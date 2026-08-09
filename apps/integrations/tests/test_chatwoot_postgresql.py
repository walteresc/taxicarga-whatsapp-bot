from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import Mock, patch
import json

from django.db import IntegrityError, close_old_connections, connection, connections
from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase, override_settings

from apps.clientes.models import Cliente
from apps.integrations.enums import AuthorType, OutboxStatus, OwnerState, Provider, SyncStatus
from apps.integrations.models import (
    BotGeneration,
    ChannelIntegrationPolicy,
    ChannelInboxMapping,
    ChatwootAccountMapping,
    ChatwootContactMapping,
    ContactInboxMapping,
    ConversationMapping,
    ConversationControl,
    ExternalMessageMapping,
    IntegrationInboxEvent,
    IntegrationMessage,
    IntegrationOutboxEvent,
)
from apps.integrations.providers.chatwoot.webhook import process_webhook
from apps.integrations.services.generations import finalize_generation, start_generation
from apps.integrations.services.human_takeover import apply_chatwoot_human_takeover
from apps.integrations.services.meta_sender import process_meta_outbox_event
from apps.integrations.services.bot_runtime import authorize_inbound_trigger
from apps.integrations.services.state_machine import return_to_bot
from apps.integrations.errors import PendingHumanOutbox
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.whatsapp.identity import resolve_whatsapp_identity


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only Chatwoot race test.")
class ChatwootMappingPostgreSQLTests(TransactionTestCase):
    def setUp(self):
        cliente = Cliente.objects.create(telefono="pg-stage5-test")
        channel = WhatsAppChannel.objects.create(
            nombre="PG Stage 5", phone_number_id="pg-stage5-no-meta", activo=False
        )
        conversation = ConversacionWhatsApp.objects.create(cliente=cliente, channel=channel)
        self.message = MensajeWhatsApp.objects.create(
            conversacion=conversation,
            direccion="entrante",
            origen="cliente",
            contenido="PG race test",
        )

    def test_two_workers_create_only_one_pending_mapping(self):
        barrier = Barrier(2, timeout=10)

        def create_mapping(_index):
            close_old_connections()
            try:
                barrier.wait()
                try:
                    ExternalMessageMapping.objects.create(
                        provider=Provider.CHATWOOT,
                        account_scope="1",
                        whatsapp_message_id=self.message.id,
                    )
                    return "created"
                except IntegrityError:
                    return "duplicate"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [future.result(timeout=20) for future in (
                executor.submit(create_mapping, 0),
                executor.submit(create_mapping, 1),
            )]

        self.assertCountEqual(results, ["created", "duplicate"])
        self.assertEqual(ExternalMessageMapping.objects.count(), 1)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only WhatsApp identity race test.")
class WhatsAppIdentityPostgreSQLTests(TransactionTestCase):
    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            nombre="PG identity", phone_number_id="pg-identity", activo=True
        )

    def test_format_variants_create_one_logical_identity_and_conversation(self):
        barrier = Barrier(2, timeout=10)

        def resolve(phone):
            close_old_connections()
            try:
                barrier.wait()
                client, _, conversation = resolve_whatsapp_identity(phone, self.channel)
                return client.id, conversation.id
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [future.result(timeout=20) for future in (
                executor.submit(resolve, "+51999999999"),
                executor.submit(resolve, "51999999999"),
            )]

        self.assertEqual(results[0], results[1])
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(ConversacionWhatsApp.objects.count(), 1)

    def test_concurrent_format_variants_keep_human_mode_and_never_call_bot(self):
        cliente = Cliente.objects.create(telefono="+51999999999")
        conversation = ConversacionWhatsApp.objects.create(
            cliente=cliente, channel=self.channel, estado_atencion="asesor", bot_pausado=True
        )
        ConversationControl.objects.create(
            conversation=conversation, owner_state=OwnerState.AGENT_ACTIVE, control_version=1
        )
        barrier = Barrier(2, timeout=10)

        def receive(index, phone):
            close_old_connections()
            payload = {
                "object": "whatsapp_business_account",
                "entry": [{"changes": [{"value": {
                    "metadata": {"phone_number_id": self.channel.phone_number_id},
                    "messages": [{
                        "id": f"wamid.pg-human-{index}", "from": phone,
                        "timestamp": "1786233150", "type": "text", "text": {"body": "Ok"},
                    }],
                }}]}],
            }
            try:
                barrier.wait()
                response = Client().post(
                    "/webhook/whatsapp/", data=json.dumps(payload), content_type="application/json"
                )
                return response.status_code, response.json().get("human_takeover")
            finally:
                connections.close_all()

        with override_settings(CHATWOOT_LIVE_SYNC_ENABLED=False), patch(
            "apps.whatsapp.views.handle_incoming_message"
        ) as ia, patch(
            "apps.whatsapp.views.send_whatsapp_message"
        ) as sender, ThreadPoolExecutor(max_workers=2) as executor:
            results = [future.result(timeout=20) for future in (
                executor.submit(receive, 1, "+51999999999"),
                executor.submit(receive, 2, "51999999999"),
            )]

        conversation.refresh_from_db()
        self.assertEqual(results, [(200, True), (200, True)])
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(ConversacionWhatsApp.objects.count(), 1)
        self.assertEqual(conversation.estado_atencion, "asesor")
        self.assertTrue(conversation.bot_pausado)
        ia.assert_not_called()
        sender.assert_not_called()
        self.assertEqual(BotGeneration.objects.count(), 0)
        self.assertEqual(IntegrationOutboxEvent.objects.count(), 0)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only Chatwoot webhook race test.")
@override_settings(CHATWOOT_ACCOUNT_ID="7", CHATWOOT_INBOX_ID="9")
class ChatwootWebhookPostgreSQLTests(TransactionTestCase):
    def setUp(self):
        cliente = Cliente.objects.create(telefono="pg-stage6-test")
        channel = WhatsAppChannel.objects.create(
            nombre="PG Stage 6", phone_number_id="pg-stage6-no-meta", activo=False
        )
        conversation = ConversacionWhatsApp.objects.create(cliente=cliente, channel=channel)
        account = ChatwootAccountMapping.objects.create(
            environment="test", account_id="7", active=True, sync_status=SyncStatus.SYNCED
        )
        inbox = ChannelInboxMapping.objects.create(
            channel=channel, account=account, inbox_id="9", inbox_identifier="pg-stage6",
            active=True, sync_status=SyncStatus.SYNCED,
        )
        contact = ChatwootContactMapping.objects.create(
            cliente=cliente, account=account, contact_id="11", active=True, sync_status=SyncStatus.SYNCED
        )
        contact_inbox = ContactInboxMapping.objects.create(
            contact=contact, inbox=inbox, source_id="pg-stage6-source", sync_status=SyncStatus.SYNCED
        )
        ConversationMapping.objects.create(
            conversation=conversation, contact_inbox=contact_inbox,
            external_conversation_id="13", active=True, sync_status=SyncStatus.SYNCED,
        )
        self.payload = {
            "event": "message_created", "id": 17, "content": "PG human race TEST",
            "message_type": "outgoing", "private": False, "sender": {"id": 3, "type": "User"},
            "account": {"id": 7}, "inbox": {"id": 9}, "conversation": {"id": 13},
        }

    def test_different_deliveries_for_same_message_create_one_effect(self):
        barrier = Barrier(2, timeout=10)

        def receive(delivery):
            close_old_connections()
            try:
                barrier.wait()
                return process_webhook(self.payload, delivery)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [future.result(timeout=20) for future in (
                executor.submit(receive, "delivery-stage6-a"),
                executor.submit(receive, "delivery-stage6-b"),
            )]

        self.assertEqual(sum(not result.duplicate for result in results), 1)
        self.assertEqual(IntegrationInboxEvent.objects.count(), 1)
        self.assertEqual(IntegrationMessage.objects.count(), 1)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only Stage 7 race tests.")
@override_settings(
    CHATWOOT_HUMAN_TAKEOVER_ENABLED=True,
    CHATWOOT_AGENT_TO_WHATSAPP_ENABLED=True,
    META_OUTBOX_ENABLED=True,
)
class Stage7PostgreSQLRaceTests(TransactionTestCase):
    def setUp(self):
        cliente = Cliente.objects.create(telefono="pg-stage7-test")
        self.channel = WhatsAppChannel.objects.create(
            nombre="PG Stage 7", phone_number_id="pg-stage7-no-meta", activo=True
        )
        ChannelIntegrationPolicy.objects.create(
            channel=self.channel, enabled=True, live_sync=True,
            human_takeover=True, return_to_bot=True, agent_outbound=True,
            commercial_labels=True, meta_outbox=True,
        )
        self.conversation = ConversacionWhatsApp.objects.create(cliente=cliente, channel=self.channel)
        self.control = ConversationControl.objects.create(conversation=self.conversation)
        account = ChatwootAccountMapping.objects.create(
            environment="test", account_id="7", active=True, sync_status=SyncStatus.SYNCED
        )
        inbox = ChannelInboxMapping.objects.create(
            channel=self.channel, account=account, inbox_id="9", inbox_identifier="pg-stage7",
            active=True, sync_status=SyncStatus.SYNCED,
        )
        contact = ChatwootContactMapping.objects.create(
            cliente=cliente, account=account, contact_id="11", active=True,
            sync_status=SyncStatus.SYNCED,
        )
        contact_inbox = ContactInboxMapping.objects.create(
            contact=contact, inbox=inbox, source_id="pg-stage7-source",
            sync_status=SyncStatus.SYNCED,
        )
        self.mapping = ConversationMapping.objects.create(
            conversation=self.conversation, contact_inbox=contact_inbox,
            external_conversation_id="13", active=True, sync_status=SyncStatus.SYNCED,
        )
    def _race(self, operation):
        barrier = Barrier(2, timeout=10)
        def run(index):
            close_old_connections()
            try:
                barrier.wait()
                return operation(index)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run, index) for index in range(2)]
            return [future.result(timeout=30) for future in futures]

    def _takeover(self, message_id):
        return apply_chatwoot_human_takeover(
            mapping_id=self.mapping.id,
            payload={"content": f"human {message_id}", "sender": {"id": 3}},
            account_id="7", inbox_id="9", message_id=str(message_id),
        )

    def test_two_human_messages_transition_once_and_create_two_outputs(self):
        self._race(lambda index: self._takeover(70 + index).transitioned)
        self.control.refresh_from_db()
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(self.control.control_version, 1)
        self.assertEqual(IntegrationMessage.objects.count(), 2)
        self.assertEqual(IntegrationOutboxEvent.objects.count(), 2)

    def test_generation_finalize_racing_takeover_has_no_bot_output_after_takeover(self):
        generation = start_generation(self.conversation.id, request_key="stage7-race")
        results = self._race(lambda index: (
            self._takeover("80").transitioned if index == 0
            else finalize_generation(generation.id, result_text="late bot")[2]
        ))
        self.control.refresh_from_db()
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertLessEqual(sum(bool(value) for value in results), 2)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(
            logical_message__author_type=AuthorType.BOT,
            status__in=[OutboxStatus.PENDING, OutboxStatus.RETRY],
        ).count(), 0)

    def test_pending_bot_outbox_racing_sender_is_suppressed_by_takeover(self):
        message = IntegrationMessage.objects.create(
            conversation=self.conversation, provider=Provider.INTERNAL, external_scope="test",
            direction="outbound", author_type=AuthorType.BOT, visibility="public",
            text="pending", idempotency_key="pending-bot",
        )
        event = IntegrationOutboxEvent.objects.create(
            destination=Provider.META_WHATSAPP, destination_scope=str(self.channel.id),
            event_type="send", logical_message=message, idempotency_key="pending-bot",
            conversation=self.conversation,
        )
        sender = Mock(return_value={"messages": [{"id": "must-not-send-after-takeover"}]})
        self._takeover("81")
        result = process_meta_outbox_event(event.id, sender=sender)
        self.assertFalse(result.sent)
        sender.assert_not_called()

    def test_two_workers_send_same_human_outbox_once(self):
        event = self._takeover("82").outbox
        sender = Mock(return_value={"messages": [{"id": "wamid.stage7.pg"}]})
        results = self._race(
            lambda index: process_meta_outbox_event(event.id, sender=sender, worker_id=f"w{index}").sent
        )
        self.assertCountEqual(results, [True, False])
        self.assertEqual(sender.call_count, 1)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only Stage 8 race tests.")
@override_settings(
    CHATWOOT_RETURN_TO_BOT_ENABLED=True,
    CHATWOOT_HUMAN_TAKEOVER_ENABLED=True,
    CHATWOOT_AGENT_TO_WHATSAPP_ENABLED=True,
)
class Stage8PostgreSQLRaceTests(TransactionTestCase):
    def setUp(self):
        self.user_id = get_user_model().objects.create_user(username="pg_stage8_advisor").id
        cliente = Cliente.objects.create(telefono="pg-stage8-client")
        self.channel = WhatsAppChannel.objects.create(
            nombre="PG Stage 8", phone_number_id="pg-stage8-phone", activo=True
        )
        ChannelIntegrationPolicy.objects.create(
            channel=self.channel, enabled=True, live_sync=True,
            human_takeover=True, return_to_bot=True, agent_outbound=True,
            commercial_labels=True, meta_outbox=True,
        )
        lead = Lead.objects.create(cliente=cliente, whatsapp_channel=self.channel)
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=cliente, lead=lead, channel=self.channel,
            estado_atencion=ConversacionWhatsApp.ATENCION_ASESOR, bot_pausado=True,
        )
        self.control = ConversationControl.objects.create(
            conversation=self.conversation, owner_state=OwnerState.AGENT_ACTIVE,
            control_version=1, active_advisor_id=self.user_id,
        )
        account = ChatwootAccountMapping.objects.create(
            environment="stage8-pg", account_id="7", active=True, sync_status=SyncStatus.SYNCED
        )
        inbox = ChannelInboxMapping.objects.create(
            channel=self.channel, account=account, inbox_id="9", inbox_identifier="stage8-pg",
            active=True, sync_status=SyncStatus.SYNCED,
        )
        contact = ChatwootContactMapping.objects.create(
            cliente=cliente, account=account, contact_id="11", active=True,
            sync_status=SyncStatus.SYNCED,
        )
        source = ContactInboxMapping.objects.create(
            contact=contact, inbox=inbox, source_id="stage8-pg-source", sync_status=SyncStatus.SYNCED
        )
        self.mapping = ConversationMapping.objects.create(
            conversation=self.conversation, contact_inbox=source,
            external_conversation_id="13", active=True, sync_status=SyncStatus.SYNCED,
        )
    def _race(self, operation):
        barrier = Barrier(2, timeout=10)

        def run(index):
            close_old_connections()
            try:
                barrier.wait()
                return operation(index)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run, index) for index in range(2)]
            return [future.result(timeout=30) for future in futures]

    def _return(self, key):
        actor = get_user_model().objects.get(pk=self.user_id)
        try:
            return return_to_bot(
                self.conversation.id, actor=actor, idempotency_key=key
            )[2]
        except PendingHumanOutbox:
            return "blocked"

    def _human(self, message_id):
        return apply_chatwoot_human_takeover(
            mapping_id=self.mapping.id,
            payload={"content": f"human {message_id}", "sender": {"id": 3}},
            account_id="7", inbox_id="9", message_id=str(message_id),
        ).transitioned

    def test_simultaneous_returns_transition_once_without_deadlock(self):
        results = self._race(lambda index: self._return(f"return-{index}"))
        self.control.refresh_from_db()
        self.assertCountEqual(results, [True, False])
        self.assertEqual(self.control.owner_state, OwnerState.BOT_ACTIVE)
        self.assertEqual(self.control.control_version, 2)

    def test_return_racing_inbound_has_single_serialized_trigger_decision(self):
        inbound = MensajeWhatsApp.objects.create(
            conversacion=self.conversation, meta_message_id="wamid-stage8-race",
            direccion="entrante", origen="cliente", contenido="race inbound",
        )
        results = self._race(lambda index: (
            self._return("return-vs-inbound") if index == 0
            else authorize_inbound_trigger(inbound.id).authorized
        ))
        self.control.refresh_from_db()
        generation_count = BotGeneration.objects.filter(input_message__external_message_id="wamid-stage8-race").count()
        self.assertIn(generation_count, {0, 1})
        if generation_count:
            self.assertEqual(self.control.owner_state, OwnerState.BOT_ACTIVE)
        self.assertEqual(sum(value is True for value in results), 1 + generation_count)

    def test_return_racing_human_message_has_deterministic_final_owner(self):
        results = self._race(lambda index: (
            self._return("return-vs-human") if index == 0 else self._human("stage8-human-race")
        ))
        self.control.refresh_from_db()
        # Human first => pending outbox blocks return. Return first => human retakes.
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(IntegrationMessage.objects.filter(author_type=AuthorType.AGENT).count(), 1)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(
            logical_message__author_type=AuthorType.AGENT
        ).count(), 1)
        self.assertNotIn(False, [value for value in results if isinstance(value, str)])

    def test_pending_human_outbox_racing_return_never_loses_message(self):
        results = self._race(lambda index: (
            self._return("pending-race-return") if index == 0 else self._human("pending-race-human")
        ))
        self.control.refresh_from_db()
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(
            logical_message__author_type=AuthorType.AGENT,
            status__in=[OutboxStatus.PENDING, OutboxStatus.RETRY, OutboxStatus.SENDING],
        ).count(), 1)

    def test_post_return_generation_racing_takeover_cannot_publish_late_bot(self):
        self._return("return-before-generation")
        inbound = MensajeWhatsApp.objects.create(
            conversacion=self.conversation, meta_message_id="wamid-stage8-generation",
            direccion="entrante", origen="cliente", contenido="new trigger",
        )
        generation = authorize_inbound_trigger(inbound.id).generation
        results = self._race(lambda index: (
            self._human("stage8-takeover-after-return") if index == 0
            else finalize_generation(generation.id, result_text="late bot")[2]
        ))
        self.control.refresh_from_db()
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(
            logical_message__author_type=AuthorType.BOT,
            status__in=[OutboxStatus.PENDING, OutboxStatus.RETRY],
        ).count(), 0)
