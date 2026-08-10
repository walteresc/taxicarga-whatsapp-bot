import hashlib
import hmac
import json
import time
from unittest.mock import patch

from django.test import override_settings

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
    IntegrationOutboxEvent,
)
from apps.integrations.providers.chatwoot.webhook import verify_signature
from apps.integrations.tests.base import IntegrationTestCase
from apps.whatsapp.models import MensajeWhatsApp


SETTINGS = {
    "CHATWOOT_WEBHOOK_ENABLED": True,
    "CHATWOOT_WEBHOOK_SECRET": "test-webhook-secret",
    "CHATWOOT_WEBHOOK_MAX_AGE_SECONDS": 300,
    "CHATWOOT_ACCOUNT_ID": "7",
    "CHATWOOT_INBOX_ID": "9",
}


@override_settings(**SETTINGS)
class ChatwootWebhookTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        account = ChatwootAccountMapping.objects.create(
            environment="test", account_id="7", active=True, sync_status=SyncStatus.SYNCED
        )
        inbox = ChannelInboxMapping.objects.create(
            channel=self.channel,
            account=account,
            inbox_id="9",
            inbox_identifier="sandbox-inbox",
            active=True,
            sync_status=SyncStatus.SYNCED,
        )
        contact = ChatwootContactMapping.objects.create(
            cliente=self.client_record,
            account=account,
            contact_id="11",
            active=True,
            sync_status=SyncStatus.SYNCED,
        )
        contact_inbox = ContactInboxMapping.objects.create(
            contact=contact, inbox=inbox, source_id="test-source", sync_status=SyncStatus.SYNCED
        )
        self.mapping = ConversationMapping.objects.create(
            conversation=self.conversation,
            contact_inbox=contact_inbox,
            external_conversation_id="13",
            active=True,
            sync_status=SyncStatus.SYNCED,
        )

    def payload(self, **overrides):
        payload = {
            "event": "message_created",
            "id": 17,
            "content": "Respuesta de asesor TEST",
            "message_type": "outgoing",
            "private": False,
            "sender": {"id": 3, "type": "User"},
            "account": {"id": 7},
            "inbox": {"id": 9},
            "conversation": {"id": 13},
            "content_attributes": {},
        }
        payload.update(overrides)
        return payload

    def post(self, payload, delivery="delivery-1", *, timestamp=None, secret="test-webhook-secret", content_type="application/json"):
        raw = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = int(time.time()) if timestamp is None else timestamp
        signature = hmac.new(
            secret.encode(), str(timestamp).encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        return self.client.post(
            "/webhooks/chatwoot/",
            data=raw,
            content_type=content_type,
            HTTP_X_CHATWOOT_TIMESTAMP=str(timestamp),
            HTTP_X_CHATWOOT_SIGNATURE=f"sha256={signature}",
            HTTP_X_CHATWOOT_DELIVERY=delivery,
        )

    def test_human_agent_creates_only_normalized_message(self):
        response = self.post(self.payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["classification"], "human_agent")
        message = IntegrationMessage.objects.get()
        self.assertEqual(message.author_type, "agent")
        self.assertEqual(message.direction, "outbound")
        self.assertEqual(message.visibility, "public")
        self.assertEqual(message.metadata["external_sender_id"], "3")
        self.assertEqual(
            IntegrationOutboxEvent.objects.filter(destination=Provider.META_WHATSAPP).count(),
            1,
        )
        self.assertEqual(MensajeWhatsApp.objects.count(), 0)
        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.bot_pausado)
        self.assertEqual(self.conversation.estado_atencion, "asesor")

    def test_same_delivery_and_new_delivery_are_idempotent(self):
        self.assertEqual(self.post(self.payload(), "delivery-a").status_code, 200)
        duplicate_delivery = self.post(self.payload(), "delivery-a")
        duplicate_message = self.post(self.payload(), "delivery-b")

        self.assertTrue(duplicate_delivery.json()["duplicate"])
        self.assertTrue(duplicate_message.json()["duplicate"])
        self.assertEqual(IntegrationInboxEvent.objects.count(), 1)
        self.assertEqual(IntegrationMessage.objects.count(), 1)

    def test_private_note_precedes_human_agent(self):
        response = self.post(self.payload(private=True))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["classification"], "private_note")
        self.assertEqual(IntegrationMessage.objects.count(), 0)

    def test_persistent_projection_mapping_precedes_human_agent(self):
        whatsapp_message = MensajeWhatsApp.objects.create(
            conversacion=self.conversation,
            direccion=MensajeWhatsApp.SALIENTE,
            origen=MensajeWhatsApp.ORIGEN_BOT,
            contenido="TEST proyectado",
        )
        ExternalMessageMapping.objects.create(
            provider=Provider.CHATWOOT,
            account_scope="7",
            external_id="17",
            whatsapp_message=whatsapp_message,
            sync_status=SyncStatus.SYNCED,
        )

        response = self.post(self.payload())

        self.assertEqual(response.json()["classification"], "django_projection")
        self.assertEqual(response.json()["action"], "ignored")
        self.assertEqual(IntegrationMessage.objects.count(), 0)

    def test_projection_metadata_is_fallback_evidence(self):
        response = self.post(self.payload(content_attributes={"taxicarga_origin": "django_projection"}))

        self.assertEqual(response.json()["classification"], "django_projection")
        self.assertEqual(IntegrationMessage.objects.count(), 0)

    def test_wrong_scopes_have_no_canonical_effects(self):
        cases = (
            (self.payload(account={"id": 999}), "wrong_account", "scope-account"),
            (self.payload(inbox={"id": 999}), "wrong_inbox", "scope-inbox"),
        )
        for payload, classification, delivery in cases:
            with self.subTest(classification=classification):
                response = self.post(payload, delivery)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["classification"], classification)
        self.assertEqual(IntegrationMessage.objects.count(), 0)
        self.assertEqual(IntegrationOutboxEvent.objects.count(), 0)
        self.assertEqual(IntegrationInboxEvent.objects.count(), 2)

    def test_unmapped_and_unsupported_return_success(self):
        unsupported = self.post(
            self.payload(id=18, sender={"type": "Contact"}, message_type="incoming"), "unsupported"
        )
        self.mapping.delete()
        unmapped = self.post(self.payload(), "unmapped")

        self.assertEqual(unmapped.status_code, 200)
        self.assertEqual(unmapped.json()["classification"], "unmapped_conversation")
        self.assertEqual(unsupported.status_code, 200)
        self.assertEqual(unsupported.json()["classification"], "unsupported")
        self.assertEqual(IntegrationMessage.objects.count(), 0)

    def test_invalid_signature_timestamp_json_and_content_type_are_rejected(self):
        self.assertEqual(self.post(self.payload(), secret="wrong").status_code, 401)
        self.assertEqual(self.post(self.payload(), timestamp=int(time.time()) - 301).status_code, 401)
        self.assertEqual(self.post(self.payload(), timestamp=int(time.time()) + 301).status_code, 401)
        self.assertEqual(self.post(self.payload(), content_type="text/plain").status_code, 415)

        raw = b"{bad"
        timestamp = int(time.time())
        signature = hmac.new(b"test-webhook-secret", str(timestamp).encode() + b"." + raw, hashlib.sha256).hexdigest()
        response = self.client.post(
            "/webhooks/chatwoot/", data=raw, content_type="application/json; charset=utf-8",
            HTTP_X_CHATWOOT_TIMESTAMP=str(timestamp),
            HTTP_X_CHATWOOT_SIGNATURE=f"sha256={signature}",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_signature_or_timestamp_is_rejected_and_get_is_not_allowed(self):
        raw = json.dumps(self.payload()).encode()
        timestamp = int(time.time())
        signature = hmac.new(
            b"test-webhook-secret", str(timestamp).encode() + b"." + raw, hashlib.sha256
        ).hexdigest()

        missing_signature = self.client.post(
            "/webhooks/chatwoot/", data=raw, content_type="application/json",
            HTTP_X_CHATWOOT_TIMESTAMP=str(timestamp),
        )
        missing_timestamp = self.client.post(
            "/webhooks/chatwoot/", data=raw, content_type="application/json",
            HTTP_X_CHATWOOT_SIGNATURE=f"sha256={signature}",
        )

        self.assertEqual(missing_signature.status_code, 401)
        self.assertEqual(missing_timestamp.status_code, 401)
        self.assertEqual(self.client.get("/webhooks/chatwoot/").status_code, 405)

    def test_signature_uses_raw_body_and_compare_digest(self):
        raw = b'{"z":1,"a":2}'
        timestamp = int(time.time())
        signature = hmac.new(
            b"test-webhook-secret", str(timestamp).encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        with patch("apps.integrations.providers.chatwoot.webhook.hmac.compare_digest", return_value=True) as compare:
            verify_signature(raw, str(timestamp), f"sha256={signature}", now=timestamp)
        compare.assert_called_once_with(signature, signature)

    def test_event_store_is_minimized(self):
        self.post(self.payload())
        safe = IntegrationInboxEvent.objects.get().safe_payload

        self.assertEqual(set(safe), {
            "event", "message_id", "conversation_id", "account_id", "inbox_id",
            "private", "sender_id", "sender_type", "classification",
            "attention_control", "performer_id", "performer_type",
            "actor_source", "actor_identity",
            "attention_control_before", "attention_control_after",
        })
        rendered = json.dumps(safe)
        self.assertNotIn("test-webhook-secret", rendered)
        self.assertNotIn("Respuesta de asesor", rendered)


class DisabledChatwootWebhookTests(IntegrationTestCase):
    @override_settings(CHATWOOT_WEBHOOK_ENABLED=False)
    def test_disabled_endpoint_is_not_operational(self):
        response = self.client.post("/webhooks/chatwoot/", data=b"{}", content_type="application/json")
        self.assertEqual(response.status_code, 404)
