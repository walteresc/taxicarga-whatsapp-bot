import json
from enum import Enum
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
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
    RESUME_PREVIOUS_REQUEST="RESUME_PREVIOUS_REQUEST"


class RequestLifecycleStatus(str,Enum):
    ACTIVE="ACTIVE"
    DORMANT="DORMANT"
    CLOSED="CLOSED"


class RequestIntentResponse(StrictModel):
    intent:RequestIntent
    confidence:float=Field(ge=0,le=1)
    clarification_text:str|None=None


# Business rule: Lead is DORMANT if no activity for this duration
INACTIVITY_THRESHOLD=timedelta(hours=2)


SYSTEM_PROMPT="""
Clasifica la intención del cliente respecto a solicitudes de servicio.

INTENTS: NEW_REQUEST, CONTINUE_REQUEST, UNCERTAIN, RESUME_PREVIOUS_REQUEST, NO_REQUEST_SIGNAL

Reglas de clasificación:

1. Si lifecycle_status=ACTIVE (solicitud vigente):
   - Respuesta clara a pregunta actual → CONTINUE_REQUEST
   - Nueva solicitud inequívoca ("otra mudanza", "nuevo servicio") → NEW_REQUEST
   - Cliente explícitamente solicita retomar histórico anterior → RESUME_PREVIOUS_REQUEST
   - Mensaje compatible con continuar pero potencialmente ambiguo → UNCERTAIN (pedir aclaración sobre solicitud actual vs nueva)
   - Saludo/duda/dato sin señal clara → NO_REQUEST_SIGNAL

2. Si lifecycle_status=DORMANT o CLOSED (solicitud inactiva/cerrada):
   - Cliente claramente solicita nuevo servicio → NEW_REQUEST
   - Cliente explícitamente desea retomar solicitud anterior → RESUME_PREVIOUS_REQUEST
   - Mensaje ambiguo o potencialmente histórico → UNCERTAIN (pedir aclaración sobre reactivación vs nueva)
   - Saludo/duda sin solicitud → NO_REQUEST_SIGNAL

3. Si lifecycle_status=null (sin solicitud asociada):
   - Cualquier solicitud clara de servicio → NEW_REQUEST
   - Saludo/duda → NO_REQUEST_SIGNAL

Criterios para RESUME_PREVIOUS_REQUEST:
- Cliente expresa explícitamente intención de reactivar/retomar: "quiero reactivar", "continúa con la anterior", "vuelvo al anterior"
- Solo válido si existe histórico disponible

Cuando uses UNCERTAIN, redacta clarification_text breve y natural que distinga entre:
- ACTIVE: solicitud actual vs. nueva solicitud
- DORMANT/CLOSED: reactivación de histórico vs. nueva solicitud

En otros casos clarification_text debe ser null.

Devuelve solo la estructura solicitada.
""".strip()


def _determine_lifecycle_status(lead,conversation):
    """Determine if lead is ACTIVE, DORMANT, or CLOSED."""
    if lead is None:
        return RequestLifecycleStatus.ACTIVE,None

    if lead.estado in {Lead.CERRADO,Lead.PERDIDO}:
        return RequestLifecycleStatus.CLOSED,lead.id

    inactivity_delta=timezone.now()-conversation.ultima_actividad
    if inactivity_delta > INACTIVITY_THRESHOLD:
        return RequestLifecycleStatus.DORMANT,lead.id

    return RequestLifecycleStatus.ACTIVE,lead.id


def classify_request_intent(*,message,active_lead,conversation,telemetry=None):
    lifecycle_status,lead_id=_determine_lifecycle_status(active_lead,conversation)

    payload={
        "current_customer_message":message,
        "lifecycle_status":lifecycle_status.value,
        "active_request":None
    }

    if active_lead is not None:
        payload["active_request"]={
            "id":active_lead.id,
            "state":active_lead.estado,
            "phase":active_lead.etapa_conversacion,
            "has_collected_data":_has_data(active_lead),
            "lifecycle_status":lifecycle_status.value
        }

    result=build_provider("conversation").generate_structured(
        [{"role":"system","content":SYSTEM_PROMPT},
         {"role":"user","content":json.dumps(payload,ensure_ascii=False)}],
        schema_model=RequestIntentResponse,purpose="classify_request_intent")
    if telemetry:
        telemetry.mark_from_ai_result("classify_request_intent",result)
    return RequestIntentResponse.model_validate_json(result.text)


def resolve_request_lifecycle(*,conversation_id,message,generation_id,telemetry=None):
    conversation=ConversacionWhatsApp.objects.select_for_update().select_related(
        "lead","cliente","channel").get(pk=conversation_id)
    old=conversation.lead
    if old is None:
        new=_new_lead(conversation)
        _switch(conversation,None,new,generation_id,RequestIntent.NEW_REQUEST)
        return new,None,RequestIntent.NEW_REQUEST
    lifecycle_status,_=_determine_lifecycle_status(old,conversation)
    try:
        result=classify_request_intent(message=message,active_lead=old,
            conversation=conversation,telemetry=telemetry)
    except Exception as exc:
        _audit(conversation,old,old,generation_id,"request_intent_failure",
               {"error_type":type(exc).__name__})
        # On exception, ask for clarification if not already pending
        if conversation.pending_request_switch:
            clarif=_clarify_active_request() if lifecycle_status==RequestLifecycleStatus.ACTIVE else _clarify_dormant_reactivation()
            return old,clarif,RequestIntent.UNCERTAIN
        conversation.pending_request_switch=True
        conversation.save(update_fields=["pending_request_switch","actualizada_en"])
        clarif=_clarify_active_request() if lifecycle_status==RequestLifecycleStatus.ACTIVE else _clarify_dormant_reactivation()
        return old,clarif,RequestIntent.UNCERTAIN
    intent=result.intent
    _audit(conversation,old,old,generation_id,"request_intent",
           {"request_intent":intent.value,"confidence":result.confidence})

    # Handle reactivation prompt rejection: if pending_request_switch and user says "no"
    if conversation.pending_request_switch and intent==RequestIntent.NO_REQUEST_SIGNAL:
        conversation.pending_request_switch=False
        conversation.save(update_fields=["pending_request_switch","actualizada_en"])
        # Return continuation intent to proceed with current lead
        return old,None,RequestIntent.CONTINUE_REQUEST

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
        clarif=result.clarification_text or (_clarify_active_request() if lifecycle_status==RequestLifecycleStatus.ACTIVE else _clarify_dormant_reactivation())
        return old,clarif,intent
    if intent==RequestIntent.RESUME_PREVIOUS_REQUEST:
        # Client explicitly wants to resume previous request (only valid if there is one)
        if not old or old.estado in {Lead.CERRADO,Lead.PERDIDO}:
            # No previous request available; treat as new
            new=_new_lead(conversation)
            _switch(conversation,old,new,generation_id,RequestIntent.NEW_REQUEST)
            return new,None,RequestIntent.NEW_REQUEST
        # Previous request exists and is valid; resume it
        old.estado=Lead.EN_CONVERSACION
        old.save(update_fields=["estado"])
        return old,None,intent
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


def _clarify_active_request():
    return "¿Deseas continuar con tu solicitud actual o mencionar una nueva?"

def _clarify_dormant_reactivation():
    return "¿Deseas reactivar tu solicitud anterior o empezar una nueva?"
