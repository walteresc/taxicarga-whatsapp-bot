import json

from .delta_contract_v31 import ConversationDeltaV31
from .providers import build_provider


DELTA_EXTRACTION_SYSTEM_PROMPT_V31 = """
Extrae un DELTA MÍNIMO: solo hechos que customer_message agrega, corrige,
aclara o confirma explícitamente. No repitas datos ya presentes en state.

EVIDENCIA OBLIGATORIA: evidence_quote y ref_evidence_quote deben ser copias
LITERALES, continuas y exactas de customer_message. Nunca expliques, resumas,
parafrasees ni fabriques evidencia. state, recent_turns y preguntas previas NO
son evidencia. Sin cita literal del mensaje actual, no propongas el cambio.

Cada claim separa evidence_type (explicit/inferred) de context_dependency
(none/question_target). explicit+none se entiende solo con customer_message;
explicit+question_target necesita last_question_targets para resolver field o
ref. Inferred significa que el cliente no afirmó el valor y será rechazado.

Si existe QuestionTarget, resuelve PRIMERO cualquier respuesta contextual con
cita literal, incluidos sí/no y respuestas breves. Después extrae TODOS los
hechos explícitos independientes adicionales, cada uno con cita propia.
QuestionTarget limita solo claims context-dependent: NO es whitelist global.
Una respuesta afirmativa/negativa al inicio aplica al target compatible. Para
cada hecho adicional usa la cita mínima que lo hace independiente; si la cita
nombra el dato por sí misma, context_dependency=none.
En target `both`, "primero" modifica SOLO origin y "segundo" SOLO destination;
no expandas uno a ambos. Si dice "solo X tiene", el otro extremo queda negativo
cuando X está inequívocamente identificado.

SERVICE es solo tipo de servicio. Oficina/traslado empresarial corresponde a
oficina. Pocos enseres u objetos de una persona corresponden a traslado pequeno;
una vivienda o conjunto doméstico corresponde a mudanza. No deduzcas service de
ruta, personal, embalaje o acceso. LOAD es solo qué se transporta; nunca quién
carga, esfuerzo, modalidad o instrucciones de embalaje. STAFF indica si se
requiere personal DE TAXICARGA para cargar/descargar. Si cliente aporta personas,
staff_required=false. Deseo incierto no fija boolean. Si QuestionTarget pregunta
packing_mode, alcance como muebles/artefactos describe embalaje, no LOAD.

Para locations usa ref_source=explicit_message SOLO si ref_evidence_quote
identifica origen/destino/ambos en customer_message; question_target SOLO si un
target compatible resuelve extremo; ambiguous si ninguno. State jamás autoriza
endpoint nuevo. No copies distritos conocidos al delta. Si observación puede
corresponder a más de un extremo, crea ambiguity y no location change.
"ambos/los dos" permite ref=both. En pregunta sobre ambos, primero/segundo refiere
origen/destino. Salida/origen/acá y llegada/destino/allá dan provenance cuando el
mensaje establece contraste. "uno" sin identificar cuál produce ambiguity.
NUNCA uses ref=both si customer_message contrasta dos cláusulas o dos lugares con
resultados distintos. En ese caso crea un location change por extremo, con cita
literal mínima de su propia cláusula. "acá ... pero allá ..." representa extremos
distintos; no combines texto completo como una observación de ambos.
Un target truck_access puede recibir observación sin boolean: conserva
access_observation y deja truck_access desconocido. Frases no métricas de acceso
(cuadras, lejos, retirado) son access_observation, nunca carry_distance_m. Sin
endpoint producen ambiguity de access_observation; con "ambos" aplican a ambos.

carry_distance_m admite solo medida numérica explícita o normalización exacta.
value_origin=derived para estimaciones; serán rechazadas. No conviertas cuadras,
cercanía o lejanía a metros. Para floor: dígito literal usa direct; cardinal u
ordinal literal inequívoco usa normalized_unit.

service_date acepta fecha explícita o relativa y no decide readiness. Fecha
relativa usa "relative:<weekday-en-inglés>"; no inventes fecha calendario sin
referencia. packing_required y packing_mode son independientes: required=true no
implica modalidad.

Si mensaje rectifica, cambia, corrige o contrasta un dato previo, incluye SIEMPRE
correction con target canónico, old/new y cita literal, además del proposed change
que fija nuevo valor. Corrections explícitas no dependen del target. Intent de
corrección sin correction es incompleto.

Nunca decidas pricing, quote/booking readiness, owner, reserva, handoff ni estado
comercial. Devuelve únicamente estructura V3.1 solicitada.
""".strip()


def extract_conversation_delta_v31(context, *, provider_name=None):
    provider = build_provider("extraction", provider_name=provider_name)
    result = provider.generate_structured(
        [{"role":"system","content":DELTA_EXTRACTION_SYSTEM_PROMPT_V31},
         {"role":"user","content":json.dumps(context.payload, ensure_ascii=False,
                                                separators=(",", ":"))}],
        schema_model=ConversationDeltaV31,
    )
    return ConversationDeltaV31.model_validate_json(result.text), result
