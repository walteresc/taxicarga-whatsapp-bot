import json
from typing import Literal

from pydantic import Field, StrictStr

from apps.integrations.models import BotGeneration

from .conversation_policy import quote_requirements
from .delta_contract import StrictModel
from .delta_snapshot import build_canonical_snapshot
from .providers import build_provider


ALLOWED_FIELDS={"service","district","floor","elevator","truck_access","load",
    "staff_required","packing_required","packing_mode","disassembly_required",
    "assembly_required","service_date","address","schedule","customer_name",
    "request_switch"}
FORBIDDEN_FIELDS={"price","discount","quote_ready","owner","commercial_status"}
LOCATION_FIELDS={"district","floor","elevator","truck_access","address"}


class AskedTarget(StrictModel):
    field: StrictStr
    ref: StrictStr | None = None
    operation: Literal["set"] = "set"


class ConversationResponse(StrictModel):
    reply_text: StrictStr = Field(min_length=1,max_length=1200)
    asked_targets: list[AskedTarget] = Field(default_factory=list,max_length=6)
    conversation_intent: Literal["ASK","CLARIFY","ANSWER_AND_ASK","INFORM",
                                 "REQUEST_SWITCH_CONFIRMATION","HANDOFF"]


SYSTEM_PROMPT="""
Actúa como asesor humano de TaxiCarga. Recibe estado ya validado y requisitos
determinísticos. Decide cómo conversar para obtener naturalmente lo pendiente.
No actúes como formulario, no repitas datos conocidos, puedes cambiar orden,
preguntar uno o varios datos compatibles, responder dudas y deferir pendientes.
asked_targets describe únicamente lo que tu reply_text pregunta realmente.
No inventes hechos, precio, descuento, readiness, reserva, ownership ni estado
comercial. Nunca calcules precio. Sé breve. Devuelve solo estructura solicitada.
""".strip()


def orchestrate_conversation(*,lead,decision,customer_message,recent_turns,generation_id,
                             last_resolution=None,telemetry=None):
    requirements=quote_requirements(lead)
    payload={"canonical_state":build_canonical_snapshot(lead).state,
        "phase":decision.phase,"required":requirements.required,
        "conditional":requirements.conditional,"optional":requirements.optional,
        "booking_only":requirements.booking_only,
        "missing_required":list(decision.missing_relevant_data),
        "customer_message":customer_message,"recent_turns":recent_turns[-4:],
        "commercial_state":{"pricing_result":decision.pricing_result,
                            "must_handoff":decision.must_handoff},
        "last_question_targets":list(last_resolution.targets) if last_resolution else [],
        "last_question_resolution_status":last_resolution.status if last_resolution else "NONE",
        "unresolved_attempts":last_resolution.unresolved_attempts if last_resolution else 0,
        "unresolved_ambiguities":[],
        "constraints":list(decision.response_constraints)+[
            "Django decides readiness, booking and pricing",
            "Do not invent price or commercial status"]}
    result=build_provider("conversation").generate_structured(
        [{"role":"system","content":SYSTEM_PROMPT},
         {"role":"user","content":json.dumps(payload,ensure_ascii=False)}],
        schema_model=ConversationResponse,purpose="orchestrate_conversation")
    if telemetry:
        telemetry.mark_from_ai_result("orchestrate_conversation",result)
    response=ConversationResponse.model_validate_json(result.text)
    targets=validate_asked_targets(response.asked_targets,payload["canonical_state"])
    _validate_continuity(response,targets,last_resolution)
    BotGeneration.objects.filter(pk=generation_id).update(asked_targets=targets,
        conversation_intent=response.conversation_intent,
        conversation_metadata={"last_question_resolution":payload["last_question_resolution_status"],
                               "unresolved_attempts":payload["unresolved_attempts"]})
    return response.reply_text,targets


def validate_asked_targets(targets,state):
    valid_refs=set(state.get("locations",{}))|{"both"}
    accepted=[]
    for target in targets:
        field=target.field
        if field in FORBIDDEN_FIELDS or field not in ALLOWED_FIELDS:
            raise ValueError("invalid conversation target field")
        if field in LOCATION_FIELDS and target.ref not in valid_refs:
            raise ValueError("invalid conversation target ref")
        if field not in LOCATION_FIELDS and target.ref is not None:
            raise ValueError("unexpected conversation target ref")
        accepted.append(target.model_dump(mode="json"))
    return accepted


def _validate_continuity(response,targets,resolution):
    if not resolution or resolution.status not in {"UNRESOLVED","AMBIGUOUS","PARTIAL"}:
        return
    if resolution.unresolved_attempts>1:return
    previous={(item.get("field"),item.get("ref")) for item in resolution.targets}
    current={(item.get("field"),item.get("ref")) for item in targets}
    if response.conversation_intent!="CLARIFY" or not previous.intersection(current):
        raise ValueError("first unresolved answer must clarify current context")
