from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.clientes.models import Cliente
from apps.integrations.enums import OwnerState
from apps.integrations.models import ConversationControl, IntegrationOutboxEvent
from apps.integrations.services.state_machine import take_conversation
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel

from ..adapters.chatwoot import ChatwootV4Adapter
from ..domain.state import BotState
from ..repositories.state import DjangoBotStateRepository
from ..services.conversation_service import ConversationService
from ..services.persistent_conversation_service import PersistentConversationService
from .fakes import ScriptedAgent, output


class ChatwootAdapterTests(TestCase):
    def setUp(self):
        self.client_record = Cliente.objects.create(telefono="51999000002")
        self.lead = Lead.objects.create(cliente=self.client_record)
        self.channel = WhatsAppChannel.objects.create(nombre="TEST V4", phone_number_id="v4-test")
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_record, lead=self.lead, channel=self.channel
        )
        self.control = ConversationControl.objects.create(conversation=self.conversation)
        self.adapter = ChatwootV4Adapter()
        self.repository = DjangoBotStateRepository()
        self.key = f"whatsapp:{self.conversation.pk}"

    def test_bot_owner_allows_v4(self):
        self.assertTrue(self.adapter.is_bot_allowed(self.conversation))

    def test_agent_owner_blocks_v4(self):
        self.control.owner_state = OwnerState.AGENT_ACTIVE
        self.control.save(update_fields=["owner_state"])
        self.assertFalse(self.adapter.is_bot_allowed(self.conversation))

    def test_agent_owner_causes_zero_llm_calls(self):
        self.control.owner_state = OwnerState.AGENT_ACTIVE
        self.control.save(update_fields=["owner_state"])
        agent = ScriptedAgent([])
        service = PersistentConversationService(
            ConversationService(agent), self.repository, chatwoot_adapter=self.adapter
        )
        result = service.process_turn(
            conversation_key=self.key, conversation=self.conversation, customer_message="primer piso"
        )
        self.assertTrue(result.turn.suppressed)
        self.assertEqual(agent.calls, 0)

    def test_return_to_bot_resumes_v4(self):
        user = get_user_model().objects.create_user(username="advisor-v4", password="x")
        take_conversation(self.conversation.id, actor=user, idempotency_key="take-v4")
        self.adapter.return_to_bot(self.conversation, actor=user, idempotency_key="return-v4")
        self.assertTrue(self.adapter.is_bot_allowed(self.conversation))

    def test_persisted_state_survives_takeover(self):
        self.repository.save(self.key, BotState(origin_district="San Isidro", destination_district="Miraflores"))
        self.control.owner_state = OwnerState.AGENT_ACTIVE
        self.control.save(update_fields=["owner_state"])
        self.assertEqual(self.repository.load(self.key).origin_district, "San Isidro")

    @patch("apps.integrations.services.live_sync.is_feature_enabled", return_value=True)
    def test_projected_customer_message_is_idempotent(self, _feature):
        message = MensajeWhatsApp.objects.create(
            conversacion=self.conversation, direccion="entrante", origen="cliente", contenido="hola"
        )
        first = self.adapter.project_customer_message(message)
        second = self.adapter.project_customer_message(message)
        self.assertEqual(first[0].pk, second[0].pk)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(idempotency_key=f"chatwoot-inbound:{message.id}").count(), 1)

    @patch("apps.integrations.services.live_sync.is_feature_enabled", return_value=True)
    def test_projected_bot_message_is_idempotent(self, _feature):
        message = MensajeWhatsApp.objects.create(
            conversacion=self.conversation, direccion="saliente", origen="bot", contenido="respuesta"
        )
        first = self.adapter.project_bot_message(message)
        second = self.adapter.project_bot_message(message)
        self.assertEqual(first[0].pk, second[0].pk)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(idempotency_key=f"chatwoot-outbound:{message.id}").count(), 1)

    def test_projection_loop_is_rejected(self):
        advisor_message = MensajeWhatsApp.objects.create(
            conversacion=self.conversation, direccion="saliente", origen="asesor", contenido="humano"
        )
        self.assertIsNone(self.adapter.project_bot_message(advisor_message))
        self.assertIsNone(self.adapter.project_customer_message(advisor_message))

    def test_private_note_is_not_projected_publicly(self):
        self.assertIsNone(self.adapter.project_private_note(object()))

    def test_chatwoot_failure_does_not_corrupt_bot_state(self):
        original = BotState(origin_district="Surco")
        self.repository.save(self.key, original)
        with patch.object(self.adapter, "project_bot_message", side_effect=RuntimeError("Chatwoot down")):
            with self.assertRaises(RuntimeError):
                self.adapter.project_bot_message(object())
        self.assertEqual(self.repository.load(self.key).origin_district, "Surco")
