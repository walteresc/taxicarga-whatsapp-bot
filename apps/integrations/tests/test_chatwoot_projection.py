from unittest.mock import Mock

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.clientes.models import Cliente
from apps.integrations.enums import Provider
from apps.integrations.models import (
    ChatwootContactMapping,
    ConversationMapping,
    ExternalMessageMapping,
)
from apps.integrations.providers.chatwoot.exceptions import (
    ChatwootConfigurationError,
    ChatwootNotFoundError,
)
from apps.integrations.services.chatwoot_projection import (
    contact_identifier,
    sync_chatwoot_conversation,
)
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel


class FakeChatwootClient:
    def __init__(self):
        self.contacts = []
        self.conversations = []
        self.messages = []
        self.posts = 0
        self.fail_message_number = None
        self.message_attempts = 0
        self.missing_contact = False
        self.missing_conversation = False
        self.requested_inboxes = []

    def get_inbox(self, inbox_id):
        self.requested_inboxes.append(str(inbox_id))
        return {"id": int(inbox_id), "channel_id": "sandbox-channel-identifier"}

    def search_contacts(self, query):
        return [item for item in self.contacts if item["identifier"] == query]

    def create_contact(self, **values):
        self.posts += 1
        contact = {
            "id": 101,
            "identifier": values["identifier"],
            "contact_inboxes": [{"source_id": "source-101", "inbox": {"id": values["inbox_id"]}}],
        }
        self.contacts.append(contact)
        return contact

    def get_contact(self, contact_id):
        if self.missing_contact:
            raise ChatwootNotFoundError("missing")
        return next(item for item in self.contacts if str(item["id"]) == str(contact_id))

    def create_contact_inbox(self, **values):
        self.posts += 1
        return {"source_id": values["source_id"]}

    def list_conversations(self, **kwargs):
        return self.conversations

    def create_conversation(self, **values):
        self.posts += 1
        conversation = {
            "id": 201,
            "additional_attributes": {"taxicarga_conversation_id": values["canonical_id"]},
        }
        self.conversations.append(conversation)
        return conversation

    def get_conversation(self, conversation_id):
        if self.missing_conversation:
            raise ChatwootNotFoundError("missing")
        return next(item for item in self.conversations if str(item["id"]) == str(conversation_id))

    def list_messages(self, conversation_id):
        return self.messages

    def create_message(self, **values):
        self.message_attempts += 1
        if self.fail_message_number == self.message_attempts:
            raise RuntimeError("simulated message failure")
        self.posts += 1
        message = {
            "id": 300 + len(self.messages) + 1,
            "content": values["content"],
            "message_type": values["message_type"],
            "content_attributes": {
                "taxicarga_message_id": values["canonical_id"],
                "taxicarga_origin": "django_projection",
            },
        }
        self.messages.append(message)
        return message


@override_settings(
    CHATWOOT_ENABLED=True,
    CHATWOOT_SYNC_ENABLED=True,
    CHATWOOT_ACCOUNT_ID="1",
    CHATWOOT_INBOX_ID="1",
)
class ChatwootProjectionTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(telefono="stage5-test", nombre="TEST Stage 5")
        self.channel = WhatsAppChannel.objects.create(
            nombre="TEST Sandbox", phone_number_id="stage5-no-meta", activo=False
        )
        self.conversation = ConversacionWhatsApp.objects.create(cliente=self.cliente, channel=self.channel)
        self.first = MensajeWhatsApp.objects.create(
            conversacion=self.conversation, direccion="entrante", origen="cliente", tipo="texto",
            contenido="same text", estado="recibido",
        )
        self.second = MensajeWhatsApp.objects.create(
            conversacion=self.conversation, direccion="saliente", origen="bot", tipo="texto",
            contenido="same text", estado="enviado", fecha_mensaje=self.first.fecha_mensaje,
        )
        self.client = FakeChatwootClient()

    @override_settings(CHATWOOT_SYNC_ENABLED=False, CHATWOOT_LIVE_SYNC_ENABLED=True)
    def test_live_projection_projects_only_explicit_new_message(self):
        result = sync_chatwoot_conversation(
            self.conversation.id,
            client=self.client,
            message_ids=[self.second.id],
            live=True,
        )
        self.assertEqual(result.total, 1)
        self.assertEqual(result.messages_created, 1)
        self.assertEqual(len(self.client.messages), 1)
        self.assertEqual(self.client.messages[0]["content"], self.second.contenido)

    @override_settings(CHATWOOT_SYNC_ENABLED=False, CHATWOOT_LIVE_SYNC_ENABLED=True)
    def test_live_projection_reuses_mapped_inbox_instead_of_global_inbox(self):
        with override_settings(CHATWOOT_SYNC_ENABLED=True, CHATWOOT_INBOX_ID="2"):
            sync_chatwoot_conversation(self.conversation.id, client=self.client)
        new_message = MensajeWhatsApp.objects.create(
            conversacion=self.conversation,
            direccion="entrante",
            origen="cliente",
            tipo="texto",
            contenido="live mapped inbox",
            estado="recibido",
        )

        result = sync_chatwoot_conversation(
            self.conversation.id,
            client=self.client,
            message_ids=[new_message.id],
            live=True,
        )

        self.assertEqual(result.messages_created, 1)
        self.assertEqual(self.client.requested_inboxes[-1], "2")

    def test_contact_identifier_is_stable_and_not_name_or_phone(self):
        self.assertEqual(contact_identifier(self.cliente.id), f"taxicarga-contact:{self.cliente.id}")

    def test_first_sync_creates_and_second_reuses_everything(self):
        first = sync_chatwoot_conversation(self.conversation.id, client=self.client)
        second = sync_chatwoot_conversation(self.conversation.id, client=self.client)

        self.assertTrue(first.contact_created)
        self.assertTrue(first.conversation_created)
        self.assertEqual(first.messages_created, 2)
        self.assertFalse(second.contact_created)
        self.assertFalse(second.conversation_created)
        self.assertEqual(second.messages_created, 0)
        self.assertEqual(second.messages_reused, 2)
        self.assertEqual(len(self.client.contacts), 1)
        self.assertEqual(len(self.client.conversations), 1)
        self.assertEqual(len(self.client.messages), 2)

    def test_messages_keep_order_direction_and_distinct_local_identity(self):
        sync_chatwoot_conversation(self.conversation.id, client=self.client)

        self.assertEqual([item["message_type"] for item in self.client.messages], ["incoming", "outgoing"])
        keys = [item["content_attributes"]["taxicarga_message_id"] for item in self.client.messages]
        self.assertEqual(keys, [f"taxicarga-message:{self.first.id}", f"taxicarga-message:{self.second.id}"])
        self.assertEqual(ExternalMessageMapping.objects.count(), 2)

    def test_partial_failure_resumes_without_duplicate(self):
        self.client.fail_message_number = 2
        first = sync_chatwoot_conversation(self.conversation.id, client=self.client)
        self.assertEqual((first.messages_created, first.messages_failed), (1, 1))
        self.assertEqual(ExternalMessageMapping.objects.count(), 1)

        self.client.fail_message_number = None
        second = sync_chatwoot_conversation(self.conversation.id, client=self.client)
        self.assertEqual((second.messages_created, second.messages_reused, second.messages_failed), (1, 1, 0))
        self.assertEqual(len(self.client.contacts), 1)
        self.assertEqual(len(self.client.conversations), 1)
        self.assertEqual(len(self.client.messages), 2)

    def test_dry_run_has_zero_http_posts_and_zero_db_mappings(self):
        result = sync_chatwoot_conversation(self.conversation.id, dry_run=True, client=Mock())

        self.assertTrue(result.dry_run)
        self.assertEqual((result.total, result.incoming, result.outgoing), (2, 1, 1))
        self.assertFalse(ChatwootContactMapping.objects.exists())
        self.assertFalse(ConversationMapping.objects.exists())
        self.assertFalse(ExternalMessageMapping.objects.exists())

    @override_settings(CHATWOOT_SYNC_ENABLED=False)
    def test_disabled_flag_makes_zero_http_calls(self):
        client = Mock()
        with self.assertRaises(ChatwootConfigurationError):
            sync_chatwoot_conversation(self.conversation.id, client=client)
        client.assert_not_called()
        self.assertEqual(client.method_calls, [])

    def test_remote_404_marks_contact_mapping_stale_and_does_not_recreate(self):
        sync_chatwoot_conversation(self.conversation.id, client=self.client)
        self.client.missing_contact = True
        posts_before = self.client.posts

        with self.assertRaises(ChatwootNotFoundError):
            sync_chatwoot_conversation(self.conversation.id, client=self.client)

        self.assertEqual(self.client.posts, posts_before)

    def test_remote_404_marks_conversation_mapping_stale_and_does_not_recreate(self):
        sync_chatwoot_conversation(self.conversation.id, client=self.client)
        self.client.missing_conversation = True
        posts_before = self.client.posts

        with self.assertRaises(ChatwootNotFoundError):
            sync_chatwoot_conversation(self.conversation.id, client=self.client)

        self.assertEqual(self.client.posts, posts_before)

    def test_constraint_blocks_duplicate_pending_mapping_for_same_message(self):
        data = {
            "provider": Provider.CHATWOOT,
            "account_scope": "1",
            "whatsapp_message": self.first,
        }
        ExternalMessageMapping.objects.create(**data)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExternalMessageMapping.objects.create(**data)
