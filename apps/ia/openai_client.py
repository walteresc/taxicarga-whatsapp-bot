import json
import logging
from datetime import date

from .prompts import EXTRACTION_SYSTEM_PROMPT, SYSTEM_PROMPT
from .providers import AIProviderError, build_provider

logger = logging.getLogger(__name__)


class ExtractionSchemaError(ValueError):
    pass


def generate_ai_result(messages, system_prompt=None, *, responsibility="conversation", provider_name=None):
    try:
        provider = build_provider(responsibility, provider_name=provider_name)
        return provider.generate(
            [
                {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
                *messages,
            ]
        )
    except Exception as exc:
        log = logger.info if isinstance(exc, AIProviderError) else logger.warning
        log(
            "Fallo provider IA; usando fallback local. provider=%s error_type=%s",
            provider_name or "configured",
            type(exc).__name__,
        )
        return None


def generate_reply(messages, system_prompt=None):
    result = generate_ai_result(messages, system_prompt, responsibility="conversation")
    return result.text if result else None


def _parse_ai_json(text):
    text = text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def _build_lead_state(lead):
    fields = [
        "tipo_servicio", "distrito_origen", "distrito_destino",
        "piso_origen", "piso_destino", "ascensor_origen", "ascensor_destino",
        "lista_objetos", "objetos_pesados", "incluye_personal_carga",
        "modalidad_servicio", "requiere_desarmado", "fecha_servicio",
        "horario_servicio", "cliente_nombre", "dni_reserva",
        "peso_carga_kg", "volumen_carga_m3",
        "direccion_origen", "direccion_destino",
        "camion_llega_origen", "camion_llega_destino",
        "distancia_carga_origen_m", "distancia_carga_destino_m",
    ]
    state = {}
    for field in fields:
        val = getattr(lead, field, None)
        if val is not None and val != "":
            if isinstance(val, date):
                state[field] = val.isoformat()
            else:
                state[field] = val
    return state


def _enrich_prompt_with_lead_state(lead_state):
    if not lead_state:
        return "El lead no tiene datos previos."
    lines = ["DATOS YA REGISTRADOS EN EL LEAD (no preguntar por estos):"]
    for field, value in lead_state.items():
        lines.append(f"  - {field}: {value}")
    return "\n".join(lines)


VALID_SERVICE_TYPES = {"mudanza", "oficina", "traslado pequeno", "carga"}
VALID_MODALITIES = {
    "sin embalaje", "embalaje basico", "embalaje básico",
    "embalaje de muebles y artefactos", "embalaje full",
}


def _sanitize_extracted(campos):
    sanitized = {}
    for field, value in campos.items():
        if value is None or value == "":
            continue
        if field == "tipo_servicio":
            if isinstance(value, str) and value.lower() in VALID_SERVICE_TYPES:
                sanitized[field] = value.lower()
        elif field in ("piso_origen", "piso_destino"):
            if isinstance(value, (int, float)) and int(value) > 0:
                sanitized[field] = int(value)
        elif field in ("ascensor_origen", "ascensor_destino", "incluye_personal_carga", "requiere_desarmado"):
            if isinstance(value, bool):
                sanitized[field] = value
        elif field == "modalidad_servicio":
            if isinstance(value, str):
                lowered = value.lower()
                for valid in VALID_MODALITIES:
                    if lowered == valid or lowered in valid:
                        sanitized[field] = valid
                        break
        elif field == "fecha_servicio":
            if isinstance(value, str):
                try:
                    from datetime import date as dt_date
                    parsed = dt_date.fromisoformat(value)
                    sanitized[field] = parsed
                except ValueError:
                    pass
        elif field in ("peso_carga_kg", "volumen_carga_m3"):
            if isinstance(value, (int, float)) and float(value) > 0:
                sanitized[field] = value
        elif field in ("camion_llega_origen", "camion_llega_destino"):
            if isinstance(value, bool):
                sanitized[field] = value
        elif field in ("distancia_carga_origen_m", "distancia_carga_destino_m"):
            if isinstance(value, (int, float)) and int(value) >= 0:
                sanitized[field] = int(value)
        elif field in ("cliente_nombre", "dni_reserva", "lista_objetos", "objetos_pesados", "horario_servicio", "direccion_origen", "direccion_destino"):
            if isinstance(value, str):
                sanitized[field] = value.strip()
        elif field in ("distrito_origen", "distrito_destino"):
            if isinstance(value, str) and len(value.strip()) > 0:
                sanitized[field] = value.strip()
    return sanitized


def extract_lead_with_ai(message, lead, recent_history=None, *, provider_name=None, raise_errors=False):
    lead_state = _build_lead_state(lead)
    lead_block = _enrich_prompt_with_lead_state(lead_state)

    today = date.today().isoformat()

    history_block = ""
    if recent_history:
        history_lines = ["CONVERSACION RECIENTE (ultimos mensajes):"]
        for entry in recent_history:
            if isinstance(entry, dict):
                history_lines.append(f"  {entry['author']}: {entry['text']}")
            else:
                history_lines.append(f"  Cliente: {entry[0]}")
                if entry[1]:
                    history_lines.append(f"  Asesor: {entry[1]}")
        history_block = "\n".join(history_lines)

    user_message = (
        f"Fecha de hoy: {today}\n\n"
        f"MENSAJE DEL CLIENTE:\n{message}\n\n"
        f"{lead_block}\n\n"
        f"{history_block}\n\n"
        "Extrae todos los campos que el cliente mencione en SU mensaje. "
        "Ignora lo que ya esta registrado en el lead. "
        "Si el cliente no menciona un campo, no lo incluyas en campos_detectados."
    )

    try:
        provider = build_provider("extraction", provider_name=provider_name)
        response = provider.generate(
            [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
        )
        text = response.text
        try:
            data = _parse_ai_json(text)
        except (json.JSONDecodeError, TypeError, AttributeError) as exc:
            raise ExtractionSchemaError("Respuesta de extracción no contiene JSON válido.") from exc
        if not isinstance(data, dict):
            raise ExtractionSchemaError("Respuesta de extracción no es un objeto JSON.")

        campos = data.get("campos_detectados", {})
        faltantes = data.get("faltantes", [])
        confianza = data.get("confianza", "baja")

        if not isinstance(campos, dict):
            campos = {}
        if not isinstance(faltantes, list):
            faltantes = []

        sanitized = _sanitize_extracted(campos)
        valid_faltantes = [f for f in faltantes if isinstance(f, str)]

        return {
            "campos_detectados": sanitized,
            "faltantes": valid_faltantes,
            "confianza": confianza if confianza in ("alta", "media", "baja") else "baja",
            "raw": campos,
            "metrics": {
                "provider": response.provider,
                "model": response.model,
                "latency_ms": response.latency_ms,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            },
        }
    except Exception as exc:
        if raise_errors:
            raise
        log = logger.info if isinstance(exc, AIProviderError) else logger.warning
        log(
            "Fallo extracción IA; usando extractor local. error_type=%s",
            type(exc).__name__,
        )
        return None


def extract_floors_with_ai(message):
    result = extract_lead_with_ai(message, _FakeLead())
    if result:
        campos = result["campos_detectados"]
        floors = {}
        if "piso_origen" in campos:
            floors["piso_origen"] = campos["piso_origen"]
        if "piso_destino" in campos:
            floors["piso_destino"] = campos["piso_destino"]
        return floors if floors else None
    return None


class _FakeLead:
    """Minimal lead mock so extract_lead_with_ai works for floor-only extraction."""
    tipo_servicio = None
    distrito_origen = None
    distrito_destino = None
    piso_origen = None
    piso_destino = None
    ascensor_origen = None
    ascensor_destino = None
    lista_objetos = None
    objetos_pesados = None
    incluye_personal_carga = None
    modalidad_servicio = None
    requiere_desarmado = None
    fecha_servicio = None
    horario_servicio = None
    cliente_nombre = None
    dni_reserva = None
    peso_carga_kg = None
    volumen_carga_m3 = None
    direccion_origen = None
    direccion_destino = None
    camion_llega_origen = None
    camion_llega_destino = None
    distancia_carga_origen_m = None
    distancia_carga_destino_m = None
