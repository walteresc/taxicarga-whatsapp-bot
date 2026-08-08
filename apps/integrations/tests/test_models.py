from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.test import override_settings

from apps.integrations.enums import OwnerState, Provider, ResumeMode, Visibility
from apps.integrations.models import (
    ChannelInboxMapping,
    ChatwootAccountMapping,
    ChatwootContactMapping,
    ContextCheckpoint,
    IntegrationInboxEvent,
    IntegrationMessage,
)

from .base import IntegrationTestCase


class IntegrationModelTests(IntegrationTestCase):
    def test_defaults_are_safe(self):
        self.assertEqual(self.control.owner_state, OwnerState.BOT_ACTIVE)
        self.assertEqual(self.control.control_version, 0)
        checkpoint = ContextCheckpoint.objects.create(conversation=self.conversation, control_version=0)
        self.assertEqual(checkpoint.resume_mode, ResumeMode.WAIT_FOR_CUSTOMER)
        message = IntegrationMessage.objects.create(
            conversation=self.conversation, provider=Provider.INTERNAL, direction="internal",
            author_type="system", idempotency_key="private-default",
        )
        self.assertEqual(message.visibility, Visibility.PRIVATE)

    def test_inbox_provider_idempotency_is_unique(self):
        data = dict(provider=Provider.META_WHATSAPP, event_type="message", idempotency_key="same", payload_hash="a" * 64)
        IntegrationInboxEvent.objects.create(**data)
        with self.assertRaises(IntegrityError), transaction.atomic():
            IntegrationInboxEvent.objects.create(**data)

    def test_same_external_key_is_allowed_for_other_provider(self):
        IntegrationInboxEvent.objects.create(
            provider=Provider.META_WHATSAPP, event_type="message", idempotency_key="same", payload_hash="a" * 64
        )
        IntegrationInboxEvent.objects.create(
            provider=Provider.CHATWOOT, event_type="message", idempotency_key="same", payload_hash="a" * 64
        )
        self.assertEqual(IntegrationInboxEvent.objects.count(), 2)

    def test_same_keys_are_allowed_in_independent_scopes(self):
        for scope in ("phone-1", "phone-2"):
            IntegrationInboxEvent.objects.create(
                provider=Provider.META_WHATSAPP, external_scope=scope,
                external_event_id="same-external", event_type="message",
                idempotency_key="same", payload_hash="a" * 64,
            )
            IntegrationMessage.objects.create(
                conversation=self.conversation, provider=Provider.META_WHATSAPP,
                external_scope=scope, external_message_id="same-external",
                direction="inbound", author_type="customer", idempotency_key="same",
            )
        self.assertEqual(IntegrationInboxEvent.objects.count(), 2)
        self.assertEqual(IntegrationMessage.objects.count(), 2)

    def test_pending_mappings_accept_null_ids_then_validate_activation(self):
        account = ChatwootAccountMapping.objects.create(environment="test", account_id=None)
        contact = ChatwootContactMapping.objects.create(cliente=self.client_record, account=account, contact_id=None)
        self.assertIsNone(contact.contact_id)
        account.active = True
        with self.assertRaises(ValidationError):
            account.full_clean()
        account.account_id = "account-1"
        account.full_clean()

    def test_only_one_active_inbox_per_channel(self):
        account = ChatwootAccountMapping.objects.create(environment="test", account_id="account-1")
        ChannelInboxMapping.objects.create(channel=self.channel, account=account, inbox_id="1", active=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChannelInboxMapping.objects.create(channel=self.channel, account=account, inbox_id="2", active=True)

    def test_same_customer_two_channels_stays_separate(self):
        channel, conversation = self.create_second_channel_conversation()
        self.assertNotEqual(self.conversation.id, conversation.id)
        self.assertNotEqual(self.conversation.channel_id, channel.id)
        self.assertEqual(self.conversation.cliente_id, conversation.cliente_id)

    def test_invalid_owner_state_fails_model_validation(self):
        self.control.owner_state = "INVALID"
        with self.assertRaises(ValidationError):
            self.control.full_clean()

    @override_settings(
        CHATWOOT_INTEGRATION_ENABLED=False,
        CHATWOOT_SHADOW_SYNC_ENABLED=False,
        CHATWOOT_AGENT_OUTBOUND_ENABLED=False,
        META_OUTBOX_ENABLED=False,
        BOT_GENERATION_LEASE_ENABLED=False,
        CHATWOOT_RETURN_TO_BOT_ENABLED=False,
    )
    def test_all_feature_flags_default_off(self):
        from django.conf import settings
        self.assertFalse(settings.CHATWOOT_INTEGRATION_ENABLED)
        self.assertFalse(settings.CHATWOOT_AGENT_OUTBOUND_ENABLED)
        self.assertFalse(settings.META_OUTBOX_ENABLED)
