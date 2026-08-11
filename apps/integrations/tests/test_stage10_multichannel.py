import json
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from apps.clientes.models import Cliente
from apps.integrations.enums import AuthorType, OutboxStatus, OwnerState, Provider, SyncStatus
from apps.integrations.models import (
    ChannelInboxMapping,
    ChannelIntegrationPolicy,
    ChatwootAccountMapping,
    ChatwootContactMapping,
    ContactInboxMapping,
    ConversationControl,
    ConversationMapping,
    IntegrationMessage,
    IntegrationOutboxEvent,
)
from apps.integrations.services.channel_policy import is_feature_enabled
from apps.integrations.services.commercial_labels import queue_commercial_label_projection
from apps.integrations.services.conversation_data import (
    process_conversation_data_event, queue_conversation_data_projection,
)
from apps.integrations.services.human_takeover import apply_chatwoot_human_takeover
from apps.integrations.services.meta_sender import process_meta_outbox_event
from apps.integrations.services.state_machine import return_to_bot
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel
from apps.whatsapp.services import send_whatsapp_template_message


@override_settings(
    CHATWOOT_LIVE_SYNC_ENABLED=True,
    CHATWOOT_HUMAN_TAKEOVER_ENABLED=True,
    CHATWOOT_RETURN_TO_BOT_ENABLED=True,
    CHATWOOT_AGENT_TO_WHATSAPP_ENABLED=True,
    CHATWOOT_COMMERCIAL_LABELS_ENABLED=True,
    META_OUTBOX_ENABLED=True,
    WHATSAPP_ACCESS_TOKEN="test-token",
    WHATSAPP_PHONE_NUMBER_ID="global-must-not-be-used",
)
class Stage10MultiChannelTests(TestCase):
    def setUp(self):
        self.customer = Cliente.objects.create(telefono="51955550320")
        self.channel_a = WhatsAppChannel.objects.create(
            nombre="A", phone_number_id="phone-a", activo=True,
        )
        self.channel_b = WhatsAppChannel.objects.create(
            nombre="B", phone_number_id="phone-b", activo=True,
        )
        self.policy_a = ChannelIntegrationPolicy.objects.create(
            channel=self.channel_a, enabled=True, live_sync=True,
            human_takeover=True, return_to_bot=True, agent_outbound=True,
            commercial_labels=True, meta_outbox=True,
        )
        self.lead_a = Lead.objects.create(cliente=self.customer, whatsapp_channel=self.channel_a)
        self.lead_b = Lead.objects.create(cliente=self.customer, whatsapp_channel=self.channel_b)
        self.conversation_a = ConversacionWhatsApp.objects.create(
            cliente=self.customer, lead=self.lead_a, channel=self.channel_a,
        )
        self.conversation_b = ConversacionWhatsApp.objects.create(
            cliente=self.customer, lead=self.lead_b, channel=self.channel_b,
        )
        self.control_a = ConversationControl.objects.create(conversation=self.conversation_a)
        self.control_b = ConversationControl.objects.create(conversation=self.conversation_b)
        self.mapping_a = self._mapping(self.conversation_a, "10", "20", "source-a")
        self.mapping_b = self._mapping(self.conversation_b, "11", "21", "source-b")

    def _mapping(self, conversation, inbox_id, conversation_id, source_id):
        account, _ = ChatwootAccountMapping.objects.get_or_create(
            environment="test", account_id="1",
            defaults={"active": True, "sync_status": SyncStatus.SYNCED},
        )
        inbox = ChannelInboxMapping.objects.create(
            channel=conversation.channel, account=account, inbox_id=inbox_id,
            inbox_identifier=f"inbox-{inbox_id}", active=True, sync_status=SyncStatus.SYNCED,
        )
        contact, _ = ChatwootContactMapping.objects.get_or_create(
            cliente=self.customer, account=account,
            defaults={"contact_id": "30", "active": True, "sync_status": SyncStatus.SYNCED},
        )
        source = ContactInboxMapping.objects.create(
            contact=contact, inbox=inbox, source_id=source_id, sync_status=SyncStatus.SYNCED,
        )
        return ConversationMapping.objects.create(
            conversation=conversation, contact_inbox=source,
            external_conversation_id=conversation_id, active=True, sync_status=SyncStatus.SYNCED,
        )

    def test_policy_is_fail_closed_and_global_flag_is_only_kill_switch(self):
        self.assertTrue(is_feature_enabled(self.channel_a, "human_takeover"))
        self.assertFalse(is_feature_enabled(self.channel_b, "human_takeover"))
        with override_settings(CHATWOOT_HUMAN_TAKEOVER_ENABLED=False):
            self.assertFalse(is_feature_enabled(self.channel_a, "human_takeover"))

    def test_takeover_a_does_not_modify_b(self):
        result = apply_chatwoot_human_takeover(
            mapping_id=self.mapping_a.id,
            payload={"content": "human A", "sender": {"id": 7}},
            account_id="1", inbox_id="10", message_id="501",
        )
        self.control_a.refresh_from_db()
        self.control_b.refresh_from_db()
        self.conversation_b.refresh_from_db()
        self.lead_b.refresh_from_db()
        self.assertTrue(result.transitioned)
        self.assertEqual(self.control_a.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(self.control_b.owner_state, OwnerState.BOT_ACTIVE)
        self.assertFalse(self.conversation_b.bot_pausado)
        self.assertFalse(self.lead_b.bot_pausado)

    def test_structured_projection_is_isolated_by_conversation(self):
        ChannelIntegrationPolicy.objects.create(
            channel=self.channel_b, enabled=True, live_sync=True,
            human_takeover=True, return_to_bot=True, agent_outbound=True,
            commercial_labels=True, meta_outbox=True,
        )
        self.lead_a.distrito_origen = "Surco"
        self.lead_a.distrito_destino = "Miraflores"
        self.lead_a.lista_objetos = "cama"
        self.lead_a.save()
        self.lead_b.distrito_origen = "Callao"
        self.lead_b.distrito_destino = "San Isidro"
        self.lead_b.lista_objetos = "mesa"
        self.lead_b.save()
        event_a, _ = queue_conversation_data_projection(self.conversation_a.id)
        event_b, _ = queue_conversation_data_projection(self.conversation_b.id)
        client = Mock()
        client.get_conversation.return_value = {
            "custom_attributes": {"taxicarga_attention_control": "Bot"}
        }

        self.assertEqual(process_conversation_data_event(event_a.id, client=client), "sent")
        self.assertEqual(process_conversation_data_event(event_b.id, client=client), "sent")
        calls = client.update_conversation_custom_attributes.call_args_list
        self.assertEqual(calls[0].args[0], "20")
        self.assertEqual(calls[0].args[1]["taxicarga_route"], "Surco → Miraflores")
        self.assertEqual(calls[0].args[1]["taxicarga_attention_control"], "Bot")
        self.assertEqual(calls[1].args[0], "21")
        self.assertEqual(calls[1].args[1]["taxicarga_route"], "Callao → San Isidro")
        self.assertEqual(calls[1].args[1]["taxicarga_attention_control"], "Bot")

    def test_return_a_does_not_modify_b(self):
        ChannelIntegrationPolicy.objects.create(
            channel=self.channel_b, enabled=True, return_to_bot=True,
        )
        for control, conversation, lead in (
            (self.control_a, self.conversation_a, self.lead_a),
            (self.control_b, self.conversation_b, self.lead_b),
        ):
            control.owner_state = OwnerState.AGENT_ACTIVE
            control.control_version = 1
            control.save()
            conversation.estado_atencion = ConversacionWhatsApp.ATENCION_ASESOR
            conversation.bot_pausado = True
            conversation.save()
            lead.atencion_humana = True
            lead.bot_pausado = True
            lead.save()
        return_to_bot(
            self.conversation_a.id, actor_type="chatwoot_agent",
            idempotency_key="return-a",
        )
        self.control_a.refresh_from_db()
        self.control_b.refresh_from_db()
        self.assertEqual(self.control_a.owner_state, OwnerState.BOT_ACTIVE)
        self.assertEqual(self.control_b.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(self.control_b.control_version, 1)

    def test_meta_outbox_uses_a_and_rejects_scope_b_before_sender(self):
        message = IntegrationMessage.objects.create(
            conversation=self.conversation_a, provider=Provider.INTERNAL,
            external_scope="internal", direction="outbound", author_type=AuthorType.BOT,
            visibility="public", text="A", idempotency_key="a-message",
        )
        valid = IntegrationOutboxEvent.objects.create(
            destination=Provider.META_WHATSAPP, destination_scope=str(self.channel_a.id),
            event_type="send", logical_message=message, conversation=self.conversation_a,
            idempotency_key="a-valid",
        )
        sender = Mock(return_value={"messages": [{"id": "wamid-a"}]})
        result = process_meta_outbox_event(valid.id, sender=sender)
        self.assertTrue(result.sent)
        self.assertEqual(sender.call_args.kwargs["channel"], self.channel_a)

        mismatch = IntegrationOutboxEvent.objects.create(
            destination=Provider.META_WHATSAPP, destination_scope=str(self.channel_b.id),
            event_type="send", logical_message=message, conversation=self.conversation_a,
            idempotency_key="a-mismatch",
        )
        blocked_sender = Mock()
        result = process_meta_outbox_event(mismatch.id, sender=blocked_sender)
        mismatch.refresh_from_db()
        self.assertFalse(result.sent)
        self.assertEqual(mismatch.status, OutboxStatus.DEAD_LETTER)
        self.assertEqual(mismatch.error_code, "channel_scope_mismatch")
        blocked_sender.assert_not_called()

    @patch("apps.whatsapp.services.requests.post")
    def test_templates_use_explicit_channel_endpoints(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"messages": [{"id": "ok"}]}
        post.return_value = response
        send_whatsapp_template_message(self.customer.telefono, channel=self.channel_a)
        send_whatsapp_template_message(self.customer.telefono, channel=self.channel_b)
        urls = [call.args[0] for call in post.call_args_list]
        self.assertIn("/phone-a/messages", urls[0])
        self.assertIn("/phone-b/messages", urls[1])
        self.assertNotIn("global-must-not-be-used", "".join(urls))

    def test_commercial_labels_a_do_not_queue_b(self):
        self.conversation_a.estado_cotizacion = ConversacionWhatsApp.COTIZACION_PRECIO_ENVIADO
        self.conversation_a.save()
        self.conversation_b.estado_cotizacion = ConversacionWhatsApp.COTIZACION_PRECIO_ENVIADO
        self.conversation_b.save()
        event_a, created_a = queue_commercial_label_projection(self.conversation_a.id)
        event_b, created_b = queue_commercial_label_projection(self.conversation_b.id)
        self.assertTrue(created_a)
        self.assertEqual(event_a.safe_payload["conversation_mapping_id"], self.mapping_a.id)
        self.assertIsNone(event_b)
        self.assertFalse(created_b)

    def test_contact_is_shared_but_sources_and_conversations_are_per_inbox(self):
        self.assertEqual(ChatwootContactMapping.objects.count(), 1)
        self.assertNotEqual(
            self.mapping_a.contact_inbox.source_id,
            self.mapping_b.contact_inbox.source_id,
        )
        self.assertNotEqual(
            self.mapping_a.contact_inbox.inbox_id,
            self.mapping_b.contact_inbox.inbox_id,
        )


class Stage10InboundFailClosedTests(TestCase):
    def _payload(self, phone_number_id, message_id):
        return {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"value": {
                "metadata": {"phone_number_id": phone_number_id},
                "messages": [{
                    "id": message_id, "from": "51955550320", "timestamp": "1786233150",
                    "type": "text", "text": {"body": "private content"},
                }],
            }}]}],
        }

    def test_unknown_channel_is_acknowledged_without_customer_or_bot(self):
        with patch("apps.whatsapp.views.handle_incoming_message") as bot:
            response = self.client.post(
                "/webhook/whatsapp/", data=json.dumps(self._payload("unknown", "unknown-1")),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reason"], "unknown_channel")
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertEqual(ConversacionWhatsApp.objects.count(), 0)
        bot.assert_not_called()

    def test_inactive_channel_is_acknowledged_without_customer_or_bot(self):
        channel = WhatsAppChannel.objects.create(
            nombre="inactive", phone_number_id="inactive", activo=False,
        )
        with patch("apps.whatsapp.views.handle_incoming_message") as bot:
            response = self.client.post(
                "/webhook/whatsapp/", data=json.dumps(self._payload(channel.phone_number_id, "inactive-1")),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reason"], "inactive_channel")
        self.assertEqual(Cliente.objects.count(), 0)
        bot.assert_not_called()
