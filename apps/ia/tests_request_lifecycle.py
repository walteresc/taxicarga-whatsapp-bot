from unittest.mock import patch

from django.test import TestCase

from apps.clientes.models import Cliente
from apps.integrations.models import ConversationControl,ConversationTransitionAudit
from apps.leads.models import Lead,LeadUbicacion
from apps.whatsapp.models import ConversacionWhatsApp,MensajeWhatsApp,WhatsAppChannel

from .conversation_resolution import last_question_resolution
from .models import AIDeltaAudit
from .request_lifecycle import RequestIntent,RequestIntentResponse,resolve_request_lifecycle


class RequestLifecycleTests(TestCase):
    def setUp(self):
        self.client=Cliente.objects.create(telefono="51900000444")
        self.channel=WhatsAppChannel.objects.create(nombre="TEST lifecycle",phone_number_id="life")
        self.old=Lead.objects.create(cliente=self.client,whatsapp_channel=self.channel,
            tipo_servicio="mudanza",lista_objetos="cama",estado=Lead.DATOS_INCOMPLETOS)
        LeadUbicacion.objects.create(lead=self.old,orden=0,tipo="origen",distrito="Surco")
        LeadUbicacion.objects.create(lead=self.old,orden=1,tipo="destino",distrito="Miraflores")
        self.conversation=ConversacionWhatsApp.objects.create(cliente=self.client,
            channel=self.channel,lead=self.old)
        ConversationControl.objects.create(conversation=self.conversation)

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_explicit_new_request_switches_to_clean_lead_and_preserves_old(self,classify):
        classify.return_value=RequestIntentResponse(intent=RequestIntent.NEW_REQUEST,
            confidence=.99,clarification_text=None)
        new,reply,intent=resolve_request_lifecycle(conversation_id=self.conversation.id,
            message="otra solicitud",generation_id="g1")
        self.assertIsNone(reply);self.assertEqual(intent,RequestIntent.NEW_REQUEST)
        self.assertNotEqual(new.id,self.old.id)
        self.assertFalse(new.tipo_servicio);self.assertFalse(new.ubicaciones.exists())
        self.old.refresh_from_db();self.assertEqual(self.old.estado,Lead.PERDIDO)
        self.conversation.refresh_from_db();self.assertEqual(self.conversation.lead_id,new.id)
        self.assertTrue(ConversationTransitionAudit.objects.filter(
            conversation=self.conversation,action="active_request_switched").exists())

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_ambiguous_request_asks_confirmation_without_switching(self,classify):
        classify.return_value=RequestIntentResponse(intent=RequestIntent.UNCERTAIN,confidence=.8,
            clarification_text="¿Seguimos con la anterior o hacemos otra?")
        lead,reply,_=resolve_request_lifecycle(conversation_id=self.conversation.id,
            message="quiero cotizar",generation_id="g2")
        self.assertEqual(lead.id,self.old.id);self.assertIn("anterior",reply)
        self.conversation.refresh_from_db();self.assertTrue(self.conversation.pending_request_switch)

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_continue_keeps_active_request(self,classify):
        classify.return_value=RequestIntentResponse(intent=RequestIntent.CONTINUE_REQUEST,
            confidence=.99,clarification_text=None)
        lead,reply,_=resolve_request_lifecycle(conversation_id=self.conversation.id,
            message="continuemos",generation_id="g3")
        self.assertEqual(lead.id,self.old.id);self.assertIsNone(reply)


class ConversationResolutionTests(TestCase):
    def setUp(self):
        client=Cliente.objects.create(telefono="51900000333")
        channel=WhatsAppChannel.objects.create(nombre="TEST recovery",phone_number_id="recover")
        lead=Lead.objects.create(cliente=client,whatsapp_channel=channel)
        self.conversation=ConversacionWhatsApp.objects.create(cliente=client,channel=channel,lead=lead)
        self.lead=lead

    def _turn(self,targets,accepted,raw=None):
        MensajeWhatsApp.objects.create(conversacion=self.conversation,origen="bot",
            direccion="saliente",contenido="pregunta",question_targets=targets)
        inbound=MensajeWhatsApp.objects.create(conversacion=self.conversation,origen="cliente",
            direccion="entrante",contenido="respuesta")
        AIDeltaAudit.objects.create(conversation_id=self.conversation.id,message_id=inbound.id,
            lead=self.lead,state_version="v",status="accepted",accepted_delta=accepted,
            raw_delta=raw or accepted)

    def test_target_resolved(self):
        self._turn([{"field":"elevator","ref":"destination","operation":"set"}],
            {"changes":{"lead":{},"locations":[{"ref":"destination","set":{"elevator":False}}]}})
        self.assertEqual(last_question_resolution(self.conversation).status,"RESOLVED")

    def test_unintelligible_answer_stays_on_current_context(self):
        self._turn([{"field":"elevator","ref":"destination","operation":"set"}],
            {"changes":{"lead":{},"locations":[]}})
        result=last_question_resolution(self.conversation)
        self.assertEqual(result.status,"UNRESOLVED")
        self.assertEqual(result.targets[0]["field"],"elevator")

    def test_spontaneous_other_data_does_not_resolve_main_target(self):
        self._turn([{"field":"elevator","ref":"destination","operation":"set"}],
            {"changes":{"lead":{"staff_required":False},"locations":[]}})
        self.assertEqual(last_question_resolution(self.conversation).status,"UNRESOLVED")

    def test_ambiguity_is_preserved(self):
        delta={"changes":{"lead":{},"locations":[]},"ambiguities":[{"field":"elevator"}]}
        self._turn([{"field":"elevator","ref":"origin"},{"field":"elevator","ref":"destination"}],delta)
        self.assertEqual(last_question_resolution(self.conversation).status,"AMBIGUOUS")
