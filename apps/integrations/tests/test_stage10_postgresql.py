from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from unittest import skipUnless

from django.db import IntegrityError, close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings

from apps.clientes.models import Cliente
from apps.integrations.enums import AuthorType, OwnerState, Provider, SyncStatus
from apps.integrations.models import (
    ChannelInboxMapping,
    ChannelIntegrationPolicy,
    ChatwootAccountMapping,
    ConversationControl,
    IntegrationMessage,
    IntegrationOutboxEvent,
)
from apps.integrations.services.meta_sender import process_meta_outbox_event
from apps.whatsapp.identity import resolve_whatsapp_identity
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only Stage 10 multi-channel tests.")
@override_settings(META_OUTBOX_ENABLED=True)
class Stage10PostgreSQLTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.channel_a = self._channel("A", "pg-phone-a")
        self.channel_b = self._channel("B", "pg-phone-b")

    def _channel(self, name, phone_id):
        channel = WhatsAppChannel.objects.create(
            nombre=name, phone_number_id=phone_id, activo=True,
        )
        ChannelIntegrationPolicy.objects.create(
            channel=channel, enabled=True, meta_outbox=True,
        )
        return channel

    def _race(self, operations):
        barrier = Barrier(len(operations), timeout=15)

        def run(operation):
            close_old_connections()
            try:
                barrier.wait()
                return operation()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            futures = [executor.submit(run, operation) for operation in operations]
            return [future.result(timeout=30) for future in futures]

    def test_simultaneous_inbound_identity_isolated_by_channel(self):
        results = self._race([
            lambda: resolve_whatsapp_identity("+51955550320", self.channel_a),
            lambda: resolve_whatsapp_identity("51955550320", self.channel_b),
        ])
        self.assertEqual(results[0][0].id, results[1][0].id)
        self.assertNotEqual(results[0][2].id, results[1][2].id)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(ConversacionWhatsApp.objects.count(), 2)
        self.assertEqual(
            set(ConversacionWhatsApp.objects.values_list("channel_id", flat=True)),
            {self.channel_a.id, self.channel_b.id},
        )

    def test_distinct_channel_workers_send_once_each_without_cross_channel(self):
        customer = Cliente.objects.create(telefono="51955550321")
        calls = []
        calls_lock = Lock()
        events = []
        for channel in (self.channel_a, self.channel_b):
            conversation = ConversacionWhatsApp.objects.create(cliente=customer, channel=channel)
            ConversationControl.objects.create(
                conversation=conversation, owner_state=OwnerState.BOT_ACTIVE,
            )
            message = IntegrationMessage.objects.create(
                conversation=conversation, provider=Provider.INTERNAL,
                external_scope=str(channel.id), direction="outbound",
                author_type=AuthorType.BOT, visibility="public", text=channel.nombre,
                idempotency_key=f"message-{channel.id}",
            )
            events.append(IntegrationOutboxEvent.objects.create(
                destination=Provider.META_WHATSAPP, destination_scope=str(channel.id),
                event_type="send", logical_message=message, conversation=conversation,
                idempotency_key=f"outbox-{channel.id}",
            ))

        def sender(_recipient, _text, *, channel, **_kwargs):
            with calls_lock:
                calls.append(channel.phone_number_id)
            return {"messages": [{"id": f"wamid-{channel.id}"}]}

        results = self._race([
            lambda: process_meta_outbox_event(events[0].id, sender=sender, worker_id="A"),
            lambda: process_meta_outbox_event(events[1].id, sender=sender, worker_id="B"),
        ])
        self.assertTrue(all(result.sent for result in results))
        self.assertCountEqual(calls, ["pg-phone-a", "pg-phone-b"])

    def test_concurrent_active_mapping_same_channel_finishes_with_one(self):
        account = ChatwootAccountMapping.objects.create(
            environment="pg-10a", account_id="1", active=True, sync_status=SyncStatus.SYNCED,
        )

        def create(inbox_id):
            try:
                ChannelInboxMapping.objects.create(
                    channel=self.channel_a, account=account, inbox_id=inbox_id,
                    inbox_identifier=f"inbox-{inbox_id}", active=True,
                    sync_status=SyncStatus.SYNCED,
                )
                return "created"
            except IntegrityError:
                return "duplicate"

        results = self._race([lambda: create("10"), lambda: create("11")])
        self.assertCountEqual(results, ["created", "duplicate"])
        self.assertEqual(
            ChannelInboxMapping.objects.filter(channel=self.channel_a, active=True).count(), 1,
        )

    def test_same_provider_id_is_isolated_by_phone_scope(self):
        customer = Cliente.objects.create(telefono="51955550322")
        conversations = [
            ConversacionWhatsApp.objects.create(cliente=customer, channel=channel)
            for channel in (self.channel_a, self.channel_b)
        ]
        for conversation, channel in zip(conversations, (self.channel_a, self.channel_b)):
            IntegrationMessage.objects.create(
                conversation=conversation, provider=Provider.META_WHATSAPP,
                external_scope=channel.phone_number_id, external_message_id="same-provider-id",
                direction="inbound", author_type="customer", visibility="public",
                idempotency_key="same-provider-id",
            )
        self.assertEqual(IntegrationMessage.objects.count(), 2)
