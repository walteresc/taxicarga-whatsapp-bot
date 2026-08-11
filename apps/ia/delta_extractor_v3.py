import json

from .delta_contract_v3 import ConversationDeltaV3
from .providers import build_provider


DELTA_EXTRACTION_SYSTEM_PROMPT_V3 = """
Comprendes mensajes libres de clientes de TaxiCarga. Devuelve solo el delta que
el mensaje actual agrega, corrige o aclara. State resuelve referencias; nunca
copies datos conocidos. last_question_targets es autoridad estructural sobre lo
que preguntaba el bot; last_bot_question es solo texto visible y nunca debe
parsearse para reconstruir targets.

Una respuesta contextual (si, no, creo que si, en destino, en ambos) solo puede
resolver targets compatibles. Informacion nueva explicitamente afirmada fuera
del target tambien puede incluirse. Cada valor y ref requiere evidence literal
del customer_message y evidence_type explicit, explicit_contextual o inferred.

packing_required expresa si requiere embalaje. packing_mode solo se completa si
el cliente identifica modalidad concreta. "con embalaje" implica required=true
y mode desconocido: no inventes basico/full. Observaciones como "queda lejos"
son access_observation; no concluyas truck_access ni carry_distance_m. Sin ref
de ubicacion suficiente, usa ambiguities. Target staff no autoriza service;
target packing no autoriza load sin evidencia independiente de objetos.

Conserva correcciones expresas. No decidas pricing, readiness, owner, reserva ni
estado comercial. Tolera typos y lenguaje coloquial.
""".strip()


def extract_conversation_delta_v3(context, *, provider_name=None):
    provider = build_provider("extraction", provider_name=provider_name)
    result = provider.generate_structured(
        [{"role": "system", "content": DELTA_EXTRACTION_SYSTEM_PROMPT_V3},
         {"role": "user", "content": json.dumps(
             context.payload, ensure_ascii=False, separators=(",", ":"))}],
        schema_model=ConversationDeltaV3,
    )
    return ConversationDeltaV3.model_validate_json(result.text), result
