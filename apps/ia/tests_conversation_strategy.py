from django.test import TestCase

from apps.clientes.models import Cliente
from apps.leads.models import Lead,LeadUbicacion
from apps.whatsapp.models import ConversacionWhatsApp,MensajeWhatsApp,WhatsAppChannel

from .conversation_policy import decide_conversation
from .conversation_strategy import select_next_conversation_goal
from .models import AIDeltaAudit


class ConversationStrategyTests(TestCase):
    def setUp(self):
        client=Cliente.objects.create(telefono="51900000888")
        channel=WhatsAppChannel.objects.create(nombre="TEST strategy",phone_number_id="strategy")
        self.lead=Lead.objects.create(
            cliente=client,whatsapp_channel=channel,tipo_servicio="mudanza",
            lista_objetos="cama",incluye_personal_carga=True,
            modalidad_servicio="sin embalaje",requiere_desarmado=False,
            requiere_armado=False)
        LeadUbicacion.objects.create(
            lead=self.lead,orden=0,tipo="origen",distrito="Surco",piso=1)
        LeadUbicacion.objects.create(
            lead=self.lead,orden=1,tipo="destino",distrito="Miraflores",piso=2)
        self.conversation=ConversacionWhatsApp.objects.create(
            cliente=client,lead=self.lead,channel=channel)

    def decision(self):return decide_conversation(self.lead,requires_truck_access=True)

    def unanswered(self,targets):
        bot=MensajeWhatsApp.objects.create(
            conversacion=self.conversation,origen=MensajeWhatsApp.ORIGEN_BOT,
            direccion=MensajeWhatsApp.SALIENTE,contenido="pregunta",question_targets=targets)
        inbound=MensajeWhatsApp.objects.create(
            conversacion=self.conversation,origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            direccion=MensajeWhatsApp.ENTRANTE,contenido="respuesta ambigua")
        AIDeltaAudit.objects.create(
            conversation_id=self.conversation.id,message_id=inbound.id,lead=self.lead,
            state_version="v",status="accepted",accepted_delta={"changes":{"lead":{},"locations":[]}})
        return bot,inbound

    def test_independent_boole_are_not_grouped(self):
        strategy=select_next_conversation_goal(self.lead,self.decision())
        self.assertEqual(len(strategy.targets),1)
        self.assertEqual(strategy.targets[0].field,"elevator")

    def test_unanswered_target_clarifies_then_defers(self):
        target=[{"field":"elevator","ref":"destination","operation":"set"}]
        self.unanswered(target)
        strategy=select_next_conversation_goal(self.lead,self.decision())
        self.assertEqual(strategy.action,"clarify")
        self.unanswered(target)
        strategy=select_next_conversation_goal(self.lead,self.decision())
        self.assertEqual(strategy.action,"defer")
        self.assertNotEqual(strategy.targets[0].field,"elevator")

    def test_resolved_field_disappears_from_next_goal(self):
        destination=self.lead.ubicaciones.get(tipo="destino")
        destination.ascensor=False;destination.save(update_fields=["ascensor"])
        strategy=select_next_conversation_goal(self.lead,self.decision())
        self.assertNotIn(("elevator","destination"),
            [(target.field,target.ref) for target in strategy.targets])
