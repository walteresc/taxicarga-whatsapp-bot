from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import IntegrityError, close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings

from apps.clientes.models import Cliente
from apps.integrations.enums import Provider, SyncStatus
from apps.integrations.models import (
    ChannelInboxMapping,
    ChatwootAccountMapping,
    ChatwootContactMapping,
    ContactInboxMapping,
    ConversationMapping,
    ExternalMessageMapping,
    IntegrationInboxEvent,
    IntegrationMessage,
)
from apps.integrations.providers.chatwoot.webhook import process_webhook
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel


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
