"""
Unified LLM inference for turn understanding.
Consolidates classify_request_intent + extract_lead_with_ai into ONE call.
Returns: request_intent, contextual_relation, extracted_fields, evidence.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from .request_lifecycle_types import RequestIntent, RequestLifecycleStatus
from .prompts import SYSTEM_PROMPT
from .providers import build_provider

logger = logging.getLogger(__name__)


@dataclass
class TurnUnderstanding:
    """Result from unified turn understanding."""
    # Lifecycle classification
    request_intent: RequestIntent
    intent_confidence: float = 0.0

    # Data extraction
    extracted_fields: Dict[str, Any] = field(default_factory=dict)
    field_evidence: Dict[str, str] = field(default_factory=dict)  # Maps field -> excerpt from message

    # Contextual analysis
    contextual_relation: str = "OTHER"  # "ANSWER", "QUESTION", "OTHER", "AMBIGUOUS"
    ambiguities: list = field(default_factory=list)

    # Telemetry
    llm_call_duration_ms: float = 0.0


def understand_turn(
    *,
    message: str,
    active_lead: Optional["Lead"],
    conversation: "ConversacionWhatsApp",
    asked_targets: Optional[list] = None,
    recent_history: Optional[list] = None,
    telemetry: Optional["Telemetry"] = None,
) -> TurnUnderstanding:
    """
    Unified LLM-based turn understanding.

    Args:
        message: Current customer message
        active_lead: Current lead or None
        conversation: ConversacionWhatsApp instance
        asked_targets: Fields we just asked for (for contextual answer detection)
        recent_history: Recent turns for context
        telemetry: Telemetry recorder

    Returns:
        TurnUnderstanding with intent, extracted fields, and evidence
    """
    import time
    from .request_lifecycle import _determine_lifecycle_status, _has_data

    start = time.time()

    # Determine lifecycle status
    lifecycle_status, _ = _determine_lifecycle_status(active_lead, conversation)

    # Build unified prompt
    payload = {
        "current_message": message,
        "lifecycle_status": lifecycle_status.value,
    }

    if active_lead:
        payload["active_request"] = {
            "id": active_lead.id,
            "state": active_lead.estado,
            "phase": active_lead.etapa_conversacion,
            "has_collected_data": _has_data(active_lead),
        }

    if asked_targets:
        payload["asked_targets"] = asked_targets

    # Build current lead context for extraction
    lead_state = {}
    if active_lead:
        lead_state = {
            "tipo_servicio": active_lead.tipo_servicio,
            "distrito_origen": active_lead.distrito_origen,
            "distrito_destino": active_lead.distrito_destino,
            "piso_origen": active_lead.piso_origen,
            "piso_destino": active_lead.piso_destino,
            "lista_objetos": active_lead.lista_objetos,
            "fecha_servicio": active_lead.fecha_servicio and active_lead.fecha_servicio.isoformat(),
        }

    payload["lead_state"] = lead_state
    payload["recent_history"] = recent_history or []

    # Make single unified LLM call
    try:
        provider = build_provider("conversation")
        result = provider.generate(
            [
                {"role": "system", "content": _UNIFIED_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
        )

        duration = (time.time() - start) * 1000
        if telemetry:
            telemetry.mark_from_ai_result("understand_turn", result)

        # Parse result
        parsed = json.loads(result.text)

        understanding = TurnUnderstanding(
            request_intent=RequestIntent(parsed.get("request_intent", "CONTINUE_REQUEST")),
            intent_confidence=float(parsed.get("intent_confidence", 0.5)),
            extracted_fields=parsed.get("extracted_fields", {}),
            field_evidence=parsed.get("field_evidence", {}),
            contextual_relation=parsed.get("contextual_relation", "OTHER"),
            ambiguities=parsed.get("ambiguities", []),
            llm_call_duration_ms=duration,
        )

        logger.debug(
            "understand_turn result intent=%s fields=%s duration=%.0fms",
            understanding.request_intent.value,
            list(understanding.extracted_fields.keys()),
            duration,
        )

        return understanding

    except Exception as exc:
        logger.exception("understand_turn LLM error: %s", type(exc).__name__)
        # Fallback: return safe default
        return TurnUnderstanding(
            request_intent=RequestIntent.CONTINUE_REQUEST,
            intent_confidence=0.0,
            extracted_fields={},
            field_evidence={},
            contextual_relation="ERROR",
            ambiguities=[str(exc)],
        )


_UNIFIED_SYSTEM_PROMPT = """Eres un asistente de conversación para cotización de servicios de mudanza y carga.

Tu tarea es analizar un mensaje de cliente en el contexto de un conversación existente.

RETORNA UN JSON CON:
{
  "request_intent": "NEW_REQUEST" | "CONTINUE_REQUEST" | "RESUME_PREVIOUS_REQUEST" | "UNCERTAIN" | "NO_REQUEST_SIGNAL",
  "intent_confidence": float 0.0-1.0,
  "contextual_relation": "ANSWER" | "QUESTION" | "OTHER" | "AMBIGUOUS",
  "extracted_fields": {
    "field_name": "extracted_value",
    ...
  },
  "field_evidence": {
    "field_name": "excerpt from message that evidences this field",
    ...
  },
  "ambiguities": ["description of any ambiguity if contextual_relation=AMBIGUOUS"]
}

REGLAS:

1. REQUEST_INTENT:
   - NEW_REQUEST: Cliente inicia una solicitud completamente nueva
   - CONTINUE_REQUEST: Cliente continúa/responde la solicitud actual (es la opción por defecto)
   - RESUME_PREVIOUS_REQUEST: Cliente quiere reactivar un request anterior (solo si dice explícitamente "reactivar", "continuar anterior", etc.)
   - UNCERTAIN: No está claro si es nuevo o continuación
   - NO_REQUEST_SIGNAL: Cliente dice "no" a una propuesta de reactivación

2. CONTEXTUAL_RELATION:
   Si asked_targets está en payload:
   - ANSWER: Mensaje responde directamente algún asked_target
   - QUESTION: Cliente hace pregunta sobre el servicio
   - OTHER: Mensaje no contesta ni es pregunta
   - AMBIGUOUS: Podría ser tanto respuesta como pregunta

3. EXTRACTED_FIELDS:
   - Solo extraer campos del payload requested (asked_targets)
   - Para cada valor extraído, proveer evidence: cita exacta del mensaje
   - Si no hay evidencia clara, NO incluir el campo
   - evidence DEBE ser el trozo exacto del mensaje que lo evidencia

4. AMBIGUITIES:
   - Si contextual_relation=AMBIGUOUS, listar qué hace ambiguo el mensaje

5. NO INVENTION:
   - NO inventes valores no evidentes en el mensaje
   - Si solo hay similitud histórica pero el cliente no lo menciona explícitamente, NO lo extraigas
"""
