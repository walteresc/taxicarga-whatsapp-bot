import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.clientes.models import Cliente
from apps.integrations.enums import OwnerState
from apps.integrations.models import ConversationControl
from apps.whatsapp.identity import AmbiguousWhatsAppIdentity, resolve_whatsapp_identity
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel


class WhatsAppPhoneIdentityTests(TestCase):
    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            nombre="Identity test", phone_number_id="identity-test", activo=True
        )

    def test_e164_stored_and_digits_incoming_resolve_same_client(self):
        stored = Cliente.objects.create(telefono="+51999999999")
        client, _, _ = resolve_whatsapp_identity("51999999999", self.channel)
        self.assertEqual(client, stored)

    def test_digits_stored_and_e164_incoming_resolve_same_client(self):
        stored = Cliente.objects.create(telefono="51999999999")
        client, _, _ = resolve_whatsapp_identity("+51999999999", self.channel)
        self.assertEqual(client, stored)

    def test_format_variants_resolve_same_channel_conversation(self):
        stored = Cliente.objects.create(telefono="+51 999-999-999")
        conversation = ConversacionWhatsApp.objects.create(cliente=stored, channel=self.channel)
        client, _, resolved = resolve_whatsapp_identity("51999999999", self.channel)
        self.assertEqual(client, stored)
        self.assertEqual(resolved, conversation)

    def test_distinct_numbers_do_not_collide(self):
        first, _, _ = resolve_whatsapp_identity("+51999999999", self.channel)
        second, _, _ = resolve_whatsapp_identity("+51999999998", self.channel)
        self.assertNotEqual(first, second)

    def test_all_supported_formats_share_identity(self):
        variants = [
            "+51 999 999 999", "51999999999", "+51999999999",
            "51-999-999-999", "(51) 999 999 999",
        ]
        results = [resolve_whatsapp_identity(value, self.channel) for value in variants]
        self.assertEqual({client.id for client, _, _ in results}, {results[0][0].id})
        self.assertEqual({conversation.id for _, _, conversation in results}, {results[0][2].id})

    def test_historical_duplicate_identity_raises_controlled_error(self):
        Cliente.objects.create(telefono="+51999999999")
        Cliente.objects.create(telefono="51-999-999-999")
        with self.assertRaises(AmbiguousWhatsAppIdentity):
            resolve_whatsapp_identity("51999999999", self.channel)

    def test_same_phone_different_channels_share_client_not_conversation(self):
        other = WhatsAppChannel.objects.create(
            nombre="Other channel", phone_number_id="identity-other", activo=True
        )
        first_client, _, first_conversation = resolve_whatsapp_identity("+51999999999", self.channel)
        second_client, _, second_conversation = resolve_whatsapp_identity("51999999999", other)
        self.assertEqual(first_client, second_client)
        self.assertNotEqual(first_conversation, second_conversation)

    @override_settings(CHATWOOT_LIVE_SYNC_ENABLED=False)
    @patch("apps.whatsapp.views.send_whatsapp_message")
    @patch("apps.whatsapp.views.handle_incoming_message")
    def test_inbound_variant_uses_human_owned_conversation_without_bot(self, ia, sender):
        client = Cliente.objects.create(telefono="+51999999999")
        conversation = ConversacionWhatsApp.objects.create(
            cliente=client, channel=self.channel,
            estado_atencion=ConversacionWhatsApp.ATENCION_ASESOR, bot_pausado=True,
        )
        ConversationControl.objects.create(
            conversation=conversation, owner_state=OwnerState.AGENT_ACTIVE, control_version=1
        )
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"value": {
                "metadata": {"phone_number_id": self.channel.phone_number_id},
                "messages": [{
                    "id": "wamid.identity-regression", "from": "51999999999",
                    "timestamp": "1786233150", "type": "text", "text": {"body": "Ok"},
                }],
            }}]}],
        }
        response = self.client.post(
            "/webhook/whatsapp/", data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["human_takeover"], True)
        self.assertEqual(Cliente.objects.filter(telefono="51999999999").count(), 0)
        self.assertEqual(ConversacionWhatsApp.objects.filter(cliente=client).count(), 1)
        ia.assert_not_called()
        sender.assert_not_called()
