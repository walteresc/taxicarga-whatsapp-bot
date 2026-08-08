from unittest.mock import patch
from uuid import uuid4

from django.test import override_settings

from apps.integrations.enums import GenerationStatus, OwnerState, Provider
from apps.integrations.errors import InvalidTransition, PrivateMessageBlocked, UnknownChannel
from apps.integrations.models import (
    BotGeneration,
    ConversationTransitionAudit,
    ExternalMessageMapping,
    IntegrationMessage,
    IntegrationOutboxEvent,
)
from apps.integrations.normalized import (
    AuthorType,
    ContentType,
    Direction,
    NormalizedAttachment,
    NormalizedMessage,
)
from apps.integrations.providers.meta_whatsapp.echoes import process_smb_message_echo, process_smb_message_echoes
from apps.integrations.services.generations import create_public_outbox

from .base import IntegrationTestCase


def normalized(**overrides):
    data = {
        "logical_message_id": uuid4(), "provider": "meta_whatsapp", "external_message_id": "external-1",
        "account_ref": "account", "channel_ref": "channel", "inbox_ref": None,
        "conversation_ref": "conversation", "sender_ref": "sender", "recipient_ref": "recipient",
        "direction": Direction.INBOUND, "author_ref": "sender", "author_type": AuthorType.CUSTOMER,
        "content_type": ContentType.TEXT, "text": "Ejemplo", "visibility": "public",
        "idempotency_key": "message-1", "correlation_id": uuid4(),
    }
    data.update(overrides)
    return NormalizedMessage(**data)


class NormalizedMessageTests(IntegrationTestCase):
    def test_text_location_interactive_and_unsupported(self):
        self.assertEqual(normalized().public_context_text(), "Ejemplo")
        self.assertEqual(normalized(content_type=ContentType.LOCATION, location=(-12.0, -77.0)).location[0], -12.0)
        self.assertEqual(normalized(
            content_type=ContentType.INTERACTIVE_REPLY,
            metadata={"interaction_id": "option", "interaction_type": "list_reply"},
        ).content_type, ContentType.INTERACTIVE_REPLY)
        self.assertEqual(normalized(content_type=ContentType.UNSUPPORTED).content_type, ContentType.UNSUPPORTED)

    def test_image_requires_attachment(self):
        with self.assertRaises(ValueError):
            normalized(content_type=ContentType.IMAGE)
        message = normalized(
            content_type=ContentType.IMAGE,
            attachments=(NormalizedAttachment("attachment", "image/example", 10),),
        )
        self.assertEqual(len(message.attachments), 1)

    def test_invalid_metadata_is_rejected(self):
        with self.assertRaises(ValueError):
            normalized(metadata={"token": "forbidden"})

    def test_invalid_runtime_types_enums_and_timestamps_are_rejected(self):
        invalid = [
            {"logical_message_id": "not-uuid"}, {"provider": "fake"},
            {"direction": "sideways"}, {"author_type": "fake"},
            {"content_type": "fake"}, {"processing_status": "fake"},
            {"correlation_id": "not-uuid"}, {"metadata": []},
            {"attachments": [NormalizedAttachment("a", "image/png")]},
            {"reply_to": ""}, {"received_at": __import__("datetime").datetime.now()},
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                normalized(**values)

    def test_content_and_author_consistency_is_enforced(self):
        with self.assertRaises(ValueError):
            normalized(direction=Direction.INBOUND, author_type=AuthorType.BOT)
        with self.assertRaises(ValueError):
            normalized(content_type=ContentType.INTERACTIVE_REPLY, metadata={})
        with self.assertRaises(ValueError):
            normalized(content_type=ContentType.LOCATION, location=(True, -77.0))

    def test_private_message_blocked_from_context_and_meta_outbox(self):
        message = normalized(visibility="private")
        with self.assertRaises(PrivateMessageBlocked):
            message.public_context_text()
        stored = IntegrationMessage.objects.create(
            conversation=self.conversation, provider=Provider.CHATWOOT, direction="internal",
            author_type="agent", visibility="private", idempotency_key="private-note",
        )
        with self.assertRaises(PrivateMessageBlocked):
            create_public_outbox(stored)


@override_settings(
    CHATWOOT_INTEGRATION_ENABLED=False,
    CHATWOOT_SHADOW_SYNC_ENABLED=False,
    CHATWOOT_AGENT_OUTBOUND_ENABLED=False,
    META_OUTBOX_ENABLED=False,
    BOT_GENERATION_LEASE_ENABLED=False,
    CHATWOOT_RETURN_TO_BOT_ENABLED=False,
)
class SmbMessageEchoTests(IntegrationTestCase):
    def echo(self, message_id="echo-1", **changes):
        value = {
            "id": message_id,
            "phone_number_id": self.channel.phone_number_id,
            "to": self.client_record.telefono,
            "type": "text",
            "text": {"body": "Respuesta humana externa"},
        }
        value.update(changes)
        return value

    @patch("requests.sessions.Session.request", side_effect=AssertionError("network forbidden"))
    def test_phone_reply_takes_control_and_only_projects_chatwoot(self, _network):
        result = process_smb_message_echo(self.echo())
        self.control.refresh_from_db()
        self.assertTrue(result.transitioned)
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(self.control.control_version, 1)
        self.assertEqual(result.message.author_type, "external_human")
        self.assertEqual(IntegrationOutboxEvent.objects.filter(destination=Provider.CHATWOOT).count(), 1)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(destination=Provider.META_WHATSAPP).count(), 0)

    def test_echo_cancels_generation_in_progress(self):
        generation = BotGeneration.objects.create(
            conversation=self.conversation, control_version_started=0,
            request_key="active", status=GenerationStatus.GENERATING,
        )
        process_smb_message_echo(self.echo())
        generation.refresh_from_db()
        self.assertEqual(generation.status, GenerationStatus.CANCELLED)
        self.assertEqual(generation.cancel_reason, "external_human_echo")

    def test_duplicate_echo_is_idempotent(self):
        first = process_smb_message_echo(self.echo())
        second = process_smb_message_echo(self.echo())
        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.assertEqual(IntegrationMessage.objects.filter(external_message_id="echo-1").count(), 1)
        self.assertEqual(IntegrationOutboxEvent.objects.count(), 1)

    def test_previously_reflected_message_is_not_duplicated(self):
        message = IntegrationMessage.objects.create(
            conversation=self.conversation, provider=Provider.META_WHATSAPP,
            external_scope=self.channel.phone_number_id, channel=self.channel,
            external_message_id="echo-existing", direction="outbound", author_type="external_human",
            visibility="public", idempotency_key="existing",
        )
        ExternalMessageMapping.objects.create(
            logical_message=message, provider=Provider.META_WHATSAPP,
            account_scope=self.channel.phone_number_id, external_id="echo-existing",
        )
        result = process_smb_message_echo(self.echo(message_id="echo-existing"))
        self.assertTrue(result.duplicate)
        self.assertEqual(IntegrationMessage.objects.filter(external_message_id="echo-existing").count(), 1)

    def test_private_echo_never_creates_message_or_outbox(self):
        with self.assertRaises(PrivateMessageBlocked):
            process_smb_message_echo(self.echo(visibility="private"))
        self.assertEqual(IntegrationMessage.objects.count(), 0)
        self.assertEqual(IntegrationOutboxEvent.objects.count(), 0)

    def test_echo_while_agent_active_does_not_increment_version(self):
        self.control.owner_state = OwnerState.AGENT_ACTIVE
        self.control.active_advisor = self.user
        self.control.control_version = 5
        self.control.save()
        result = process_smb_message_echo(self.echo())
        self.control.refresh_from_db()
        self.assertFalse(result.transitioned)
        self.assertEqual(self.control.control_version, 5)
        audit = ConversationTransitionAudit.objects.get()
        self.assertEqual(audit.actor_type, "external_human")
        self.assertEqual(audit.version_before, audit.version_after)

    def test_echo_while_waiting_transitions_once(self):
        self.control.owner_state = OwnerState.WAITING_AGENT
        self.control.control_version = 3
        self.control.save()
        process_smb_message_echo(self.echo())
        self.control.refresh_from_db()
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(self.control.control_version, 4)

    def test_echo_in_closed_state_is_rejected_without_side_effects(self):
        self.control.owner_state = OwnerState.CLOSED
        self.control.save()
        with self.assertRaises(InvalidTransition):
            process_smb_message_echo(self.echo())
        self.assertEqual(IntegrationMessage.objects.count(), 0)
        self.assertEqual(IntegrationOutboxEvent.objects.count(), 0)

    def test_physical_advisor_identity_remains_unknown(self):
        process_smb_message_echo(self.echo())
        audit = ConversationTransitionAudit.objects.get()
        self.assertIsNone(audit.actor)
        self.assertEqual(audit.external_actor_ref, "")
        self.assertFalse(audit.metadata["advisor_identity_verified"])

    def test_unknown_channel_is_rejected(self):
        with self.assertRaises(UnknownChannel):
            process_smb_message_echo(self.echo(phone_number_id="unknown-channel"))
        self.assertEqual(IntegrationMessage.objects.count(), 0)

    def test_same_customer_other_channel_is_not_mixed(self):
        other_channel, other_conversation = self.create_second_channel_conversation()
        result = process_smb_message_echo(self.echo(
            message_id="echo-other", phone_number_id=other_channel.phone_number_id
        ))
        self.assertEqual(result.message.conversation_id, other_conversation.id)

    def test_same_external_id_is_scoped_per_channel(self):
        process_smb_message_echo(self.echo(message_id="same-provider-id"))
        other_channel, other_conversation = self.create_second_channel_conversation()
        second = process_smb_message_echo(self.echo(
            message_id="same-provider-id", phone_number_id=other_channel.phone_number_id
        ))
        self.assertEqual(second.message.conversation_id, other_conversation.id)
        self.assertEqual(IntegrationMessage.objects.filter(external_message_id="same-provider-id").count(), 2)

    def test_native_envelope_routes_message_echoes(self):
        payload = {
            "entry": [{"changes": [{
                "field": "smb_message_echoes",
                "value": {
                    "metadata": {"phone_number_id": self.channel.phone_number_id},
                    "message_echoes": [{
                        "id": "echo-envelope", "to": self.client_record.telefono,
                        "type": "text", "text": {"body": "Respuesta vinculada"},
                    }],
                },
            }]}],
        }
        results = process_smb_message_echoes(payload)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].message.external_message_id, "echo-envelope")
