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
from .request_lifecycle_types import RequestIntent, RequestLifecycleStatus, INACTIVITY_THRESHOLD
from .understand_turn import understand_turn, TurnUnderstanding


class RequestIntentResponse(StrictModel):
    intent:RequestIntent
    confidence:float=Field(ge=0,le=1)
    clarification_text:str|None=None


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
    """Classify request intent. Internally calls understand_turn (consolidated inference)."""
    understanding=understand_turn(
        message=message,
        active_lead=active_lead,
        conversation=conversation,
        telemetry=telemetry
    )
    return RequestIntentResponse(
        intent=understanding.request_intent,
        confidence=understanding.intent_confidence,
        clarification_text=None
    )


def resolve_request_lifecycle(*,conversation_id,message,generation_id,telemetry=None):
    conversation=ConversacionWhatsApp.objects.select_for_update().select_related(
        "lead","cliente","channel").get(pk=conversation_id)
    old=conversation.lead
    if old is None:
        new=_new_lead(conversation)
        _switch(conversation,None,new,generation_id,RequestIntent.NEW_REQUEST)
        return new,None,RequestIntent.NEW_REQUEST
    lifecycle_status,_=_determine_lifecycle_status(old,conversation)

    # PRIORITY: Check if message is a CLEAR CONTEXTUAL ANSWER to last question
    # If yes, bypass lifecycle classification and treat as CONTINUE_REQUEST
    if _is_contextual_answer(old,conversation,message):
        # Message directly answers the last asked targets; no need for lifecycle classification
        if conversation.pending_request_switch:
            conversation.pending_request_switch=False
            conversation.save(update_fields=["pending_request_switch","actualizada_en"])
        _audit(conversation,old,old,generation_id,"contextual_answer_resolved",
               {"request_intent":RequestIntent.CONTINUE_REQUEST.value})
        return old,None,RequestIntent.CONTINUE_REQUEST

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


def _is_contextual_answer(lead,conversation,message):
    """Check if message clearly answers the last asked targets.

    CRITICAL: Separate ANSWER INTENT from FIELD EXTRACTION.
    A message can be a contextual answer attempt even if extraction is partial/imperfect.
    """
    if lead is None:
        return False

    # Get the last bot message to see what was asked
    from apps.whatsapp.models import MensajeWhatsApp
    last_bot_msg=MensajeWhatsApp.objects.filter(
        conversacion=conversation,
        direccion="SALIENTE"
    ).order_by('-creado_en').first()

    if last_bot_msg is None:
        return False

    msg_lower=last_bot_msg.contenido.lower()
    answer_lower=message.lower()

    # Route question: "¿Cuál es el distrito de partida y llegada?"
    # Accept ANY message with location-like structure when route was asked
    if any(term in msg_lower for term in ("distrito", "partida", "llegada", "origen", "destino", "de donde", "para donde", "a donde")):
        # Message must look like it's attempting to answer a route question
        # Patterns: "X a Y", "de X para Y", "X y Y", etc.
        if _looks_like_route_answer(answer_lower):
            return True

    # Floor question: "¿De qué piso sale y a qué piso llega?"
    if any(term in msg_lower for term in ("piso", "nivel", "altura", "planta")):
        # Answer should have floor numbers or clear floor references
        if _has_floor_reference(answer_lower):
            return True

    # Elevator/access question: "ascensor", "escaleras"
    if any(term in msg_lower for term in ("ascensor", "escaleras", "puerta a calle", "acceso")):
        # Answer should be yes/no or descriptive
        if _is_yes_no_or_descriptive(answer_lower):
            return True

    # Load/items question: "qué cosas"
    if any(term in msg_lower for term in ("cosas", "llevas", "trasladar", "carga")):
        # Answer should describe items (unlikely to be new request)
        if len(answer_lower) > 5:  # Not just a single word
            return True

    return False


def _looks_like_route_answer(msg):
    """Check if message has structure of a route answer, regardless of exact district match.

    Examples:
    - "surquillo a san luis"
    - "de surquillo a asn luis"
    - "la molina para miraflores"
    - "surco y san luis"
    - "de aqui a ahi"
    """
    # Route answer patterns: contain connectors like "a", "para", "y" with location-like words on both sides
    # Must have at least one connector AND at least 2 "words" that could be locations

    # Look for connectors
    has_connector=any(term in msg for term in (" a ", " para ", " y ", " del ", " de ", " para "))

    if not has_connector:
        return False

    # Split by common connectors and check we have at least 2 parts with content
    import re
    parts=[p.strip() for p in re.split(r'\ba\b|\bpara\b|\by\b|\bdel\b|\bde\b', msg) if p.strip()]

    # Must have at least 2 parts that look like locations (words, not single letters)
    meaningful_parts=[p for p in parts if len(p) > 1 and len(p.split()) >= 1]

    return len(meaningful_parts) >= 2


def _extract_locations_from_message(msg):
    """Extract possible location names from message."""
    # Known Lima districts for quick matching
    districts={
        "la molina", "san luis", "surco", "miraflores", "san isidro",
        "lima", "callao", "jesus maria", "lince", "ancón", "ate",
        "barranco", "breña", "carabayllo", "carmen de la legua",
        "cercado", "chaclacayo", "chorrillos", "cieneguilla", "comas",
        "el agustino", "independencia", "la perla", "la punta",
        "la victoria", "puente piedra", "rímac", "san bartolo",
        "san juan de lurigancho", "san juan de miraflores",
        "santa anita", "santa maría del mar", "santa rosa"
    }
    found=[]
    for district in districts:
        if district in msg:
            found.append(district)
    return found


def _has_floor_reference(msg):
    """Check if message contains clear floor references."""
    import re
    # Look for numbers (1, 2, 3, etc.) or floor words
    if re.search(r'\b\d+\b', msg):  # Any number
        return True
    if any(term in msg for term in ("primero", "segundo", "tercero", "cuarto", "quinto",
                                     "piso", "nivel", "planta", "piso bajo")):
        return True
    return False


def _is_yes_no_or_descriptive(msg):
    """Check if message is a yes/no answer or descriptive."""
    yes_terms={"sí", "si", "yes", "yep", "claro", "ok", "okis"}
    no_terms={"no", "nope"}
    if any(term in msg for term in yes_terms):
        return True
    if any(term in msg for term in no_terms):
        return True
    # Descriptive answers (longer than just one word)
    if len(msg.split()) > 2:
        return True
    return False


def _clarify_active_request():
    return "¿Deseas continuar con tu solicitud actual o mencionar una nueva?"

def _clarify_dormant_reactivation():
    return "¿Deseas reactivar tu solicitud anterior o empezar una nueva?"
