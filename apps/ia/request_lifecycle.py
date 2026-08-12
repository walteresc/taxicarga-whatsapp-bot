import json
from enum import Enum

from django.db import transaction
from pydantic import Field

from apps.integrations.enums import OwnerState
from apps.integrations.models import ConversationControl,ConversationTransitionAudit
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp

from .delta_contract import StrictModel
from .providers import build_provider


class RequestIntent(str,Enum):
    NEW_REQUEST="NEW_REQUEST"
    CONTINUE_REQUEST="CONTINUE_REQUEST"
    UNCERTAIN="UNCERTAIN"
    NO_REQUEST_SIGNAL="NO_REQUEST_SIGNAL"


class RequestIntentResponse(StrictModel):
    intent:RequestIntent
    confidence:float=Field(ge=0,le=1)
    clarification_text:str|None=None


SYSTEM_PROMPT="""
Clasifica únicamente si el mensaje actual continúa la solicitud comercial activa,
pide inequívocamente otra solicitud, o es ambiguo. No uses mensajes históricos.
Si existe una solicitud activa incompleta y el cliente solo dice que quiere cotizar
un servicio sin decir "otra/nueva/distinta" ni confirmar cambio, usa UNCERTAIN.
NEW_REQUEST requiere intención explícita de una solicitud diferente o confirmación
de cambio pendiente. Respuestas a la pregunta actual son CONTINUE_REQUEST.
Saludos, dudas y datos sin señal de cambio son NO_REQUEST_SIGNAL.
Si usas UNCERTAIN, redacta clarification_text breve y natural para confirmar si
continúa la solicitud activa o inicia otra. En los demás casos debe ser null.
Devuelve solo la estructura solicitada.
""".strip()


def classify_request_intent(*,message,active_lead,pending_switch):
    payload={"current_customer_message":message,"pending_switch":pending_switch,
             "active_request":{"id":active_lead.id,"state":active_lead.estado,
                               "phase":active_lead.etapa_conversacion,
                               "has_collected_data":_has_data(active_lead)}}
    result=build_provider("conversation").generate_structured(
        [{"role":"system","content":SYSTEM_PROMPT},
         {"role":"user","content":json.dumps(payload,ensure_ascii=False)}],
        schema_model=RequestIntentResponse)
    return RequestIntentResponse.model_validate_json(result.text)


def resolve_request_lifecycle(*,conversation_id,message,generation_id):
    conversation=ConversacionWhatsApp.objects.select_for_update().select_related(
        "lead","cliente","channel").get(pk=conversation_id)
    old=conversation.lead
    if old is None:
        new=_new_lead(conversation)
        _switch(conversation,None,new,generation_id,RequestIntent.NEW_REQUEST)
        return new,None,RequestIntent.NEW_REQUEST
    try:
        result=classify_request_intent(message=message,active_lead=old,
            pending_switch=conversation.pending_request_switch)
    except Exception as exc:
        _audit(conversation,old,old,generation_id,"request_intent_failure",
               {"error_type":type(exc).__name__})
        if conversation.pending_request_switch:
            return old,_switch_question(),RequestIntent.UNCERTAIN
        return old,None,RequestIntent.NO_REQUEST_SIGNAL
    intent=result.intent
    _audit(conversation,old,old,generation_id,"request_intent",
           {"request_intent":intent.value,"confidence":result.confidence})
    if intent==RequestIntent.NEW_REQUEST:
        new=_new_lead(conversation)
        old.estado=Lead.PERDIDO
        old.motivo_perdida="Reemplazada por nueva solicitud confirmada"
        old.save(update_fields=["estado","motivo_perdida"])
        _switch(conversation,old,new,generation_id,intent)
        return new,None,intent
    if intent==RequestIntent.UNCERTAIN:
        conversation.pending_request_switch=True
        conversation.save(update_fields=["pending_request_switch","actualizada_en"])
        return old,result.clarification_text or _switch_question(),intent
    if conversation.pending_request_switch and intent==RequestIntent.CONTINUE_REQUEST:
        conversation.pending_request_switch=False
        conversation.save(update_fields=["pending_request_switch","actualizada_en"])
    return old,None,intent


def _has_data(lead):
    return bool(lead.tipo_servicio or lead.lista_objetos or lead.ubicaciones.exists())


def _new_lead(conversation):
    return Lead.objects.create(cliente=conversation.cliente,whatsapp_channel=conversation.channel,
                               estado=Lead.NUEVO)


def _switch(conversation,old,new,generation_id,intent):
    conversation.lead=new
    conversation.pending_request_switch=False
    conversation.estado_recopilacion=ConversacionWhatsApp.RECOPILACION_NUEVA
    conversation.estado_cotizacion=ConversacionWhatsApp.COTIZACION_SIN_INICIAR
    conversation.datos_faltantes=[]
    conversation.porcentaje_informacion=0
    conversation.save(update_fields=["lead","pending_request_switch","estado_recopilacion",
        "estado_cotizacion","datos_faltantes","porcentaje_informacion","actualizada_en"])
    _audit(conversation,old,new,generation_id,"active_request_switched",
           {"request_intent":intent.value})


def _audit(conversation,old,new,generation_id,action,metadata):
    control,_=ConversationControl.objects.get_or_create(conversation=conversation)
    ConversationTransitionAudit.objects.get_or_create(
        conversation=conversation,action=action,idempotency_key=f"generation:{generation_id}:{action}",
        defaults={"from_state":control.owner_state,"to_state":control.owner_state,
            "actor_type":"system","source":"request_lifecycle",
            "version_before":control.control_version,"version_after":control.control_version,
            "reason":"request lifecycle","metadata":{
                "active_request_id_before":getattr(old,"id",None),
                "active_request_id_after":getattr(new,"id",None),**metadata}})


def _switch_question():
    return "¿Quieres continuar con la cotización anterior o empezar una nueva?"
