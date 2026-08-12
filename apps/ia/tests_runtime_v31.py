from unittest.mock import patch

from django.test import TestCase,override_settings
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.clientes.models import Cliente
from apps.integrations.models import ChannelIntegrationPolicy,IntegrationOutboxEvent
from apps.integrations.services.bot_generation_worker import (
    BOT_GENERATION_EVENT,queue_bot_generation,
)
from apps.integrations.services.channel_policy import ai_v31_mode
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp,MensajeWhatsApp,WhatsAppChannel

from .delta_contract_v31 import ConversationDeltaV31
from .providers import AIResult
from .runtime_v31 import extract_runtime_v31


class RuntimeV31Tests(TestCase):
    def setUp(self):
        self.channel=WhatsAppChannel.objects.create(nombre="TEST V31",phone_number_id="v31-test")
        self.policy=ChannelIntegrationPolicy.objects.create(
            channel=self.channel,enabled=True,ai_v31_mode="active")
        self.client_record=Cliente.objects.create(nombre="Test",telefono="51900000001")
        self.lead=Lead.objects.create(cliente=self.client_record,whatsapp_channel=self.channel)
        self.conversation=ConversacionWhatsApp.objects.create(
            cliente=self.client_record,lead=self.lead,channel=self.channel)
        self.message=MensajeWhatsApp.objects.create(
            conversacion=self.conversation,origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            tipo="texto",contenido="Mudanza de Surco a Miraflores")

    def test_policy_is_per_channel_and_defaults_off(self):
        other=WhatsAppChannel.objects.create(nombre="REAL",phone_number_id="real-off")
        self.assertEqual(ai_v31_mode(self.channel),"active")
        self.assertEqual(ai_v31_mode(other),"off")

    @patch("apps.ia.runtime_v31.extract_conversation_delta_v31")
    def test_validated_delta_maps_to_runtime_fields_idempotently(self,extract):
        delta=ConversationDeltaV31.model_validate({"intent":"provide_information",
            "changes":{"lead":{"service":{"value":"mudanza","evidence_quote":"Mudanza",
            "evidence_type":"explicit","context_dependency":"none"}},"locations":[
            {"ref":"origin","ref_evidence_quote":"Surco","ref_source":"explicit_message",
             "set":{"district":{"value":"Surco","evidence_quote":"Surco",
             "evidence_type":"explicit","context_dependency":"none"}}},
            {"ref":"destination","ref_evidence_quote":"Miraflores","ref_source":"explicit_message",
             "set":{"district":{"value":"Miraflores","evidence_quote":"Miraflores",
             "evidence_type":"explicit","context_dependency":"none"}}}]}})
        extract.return_value=(delta,AIResult("{}","openai","gpt-4.1-mini",1,2,3))
        first,audit=extract_runtime_v31(lead=self.lead,conversation_id=self.conversation.id,
            message_id=self.message.id,customer_message=self.message.contenido,mode="active")
        second,same=extract_runtime_v31(lead=self.lead,conversation_id=self.conversation.id,
            message_id=self.message.id,customer_message=self.message.contenido,mode="active")
        self.assertEqual(first,second)
        self.assertEqual(first["tipo_servicio"],"mudanza")
        self.assertEqual(first["distrito_origen"],"Surco")
        self.assertEqual(audit.pk,same.pk)
        self.assertEqual(audit.schema_version,31)

    def test_generation_work_is_idempotent_internal_outbox(self):
        from apps.integrations.models import BotGeneration,ConversationControl
        from apps.integrations.enums import GenerationStatus
        ConversationControl.objects.create(conversation=self.conversation)
        generation=BotGeneration.objects.create(conversation=self.conversation,
            control_version_started=0,status=GenerationStatus.GENERATING,request_key="test")
        first,created=queue_bot_generation(message_id=self.message.id,generation_id=generation.id)
        second,created_again=queue_bot_generation(message_id=self.message.id,generation_id=generation.id)
        self.assertTrue(created);self.assertFalse(created_again)
        self.assertEqual(first.pk,second.pk)
        self.assertEqual(first.event_type,BOT_GENERATION_EVENT)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(event_type=BOT_GENERATION_EVENT).count(),1)

    def test_active_command_rejects_non_test_channel_and_rolls_back(self):
        other=WhatsAppChannel.objects.create(nombre="Canal real",phone_number_id="real-safe")
        with self.assertRaises(CommandError):call_command("set_ai_v31_mode",other.id,"active")
        call_command("set_ai_v31_mode",self.channel.id,"off")
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.ai_v31_mode,"off")

    @patch("apps.integrations.services.bot_generation_worker.handle_incoming_message",
           return_value="Respuesta segura")
    def test_worker_publishes_once_without_physical_send(self,_handle):
        from apps.integrations.models import BotGeneration,ConversationControl
        from apps.integrations.enums import GenerationStatus,OutboxStatus,Provider
        from apps.integrations.services.bot_generation_worker import process_bot_generation_event
        ConversationControl.objects.create(conversation=self.conversation)
        generation=BotGeneration.objects.create(conversation=self.conversation,
            control_version_started=0,status=GenerationStatus.GENERATING,request_key="worker")
        event,_=queue_bot_generation(message_id=self.message.id,generation_id=generation.id)
        self.assertEqual(process_bot_generation_event(event.id,worker_id="test"),"published")
        self.assertEqual(process_bot_generation_event(event.id,worker_id="test"),"already_sent")
        event.refresh_from_db();generation.refresh_from_db()
        self.assertEqual(event.status,OutboxStatus.SENT)
        self.assertEqual(generation.status,GenerationStatus.PUBLISHED)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(
            destination=Provider.META_WHATSAPP,status=OutboxStatus.PENDING).count(),1)
