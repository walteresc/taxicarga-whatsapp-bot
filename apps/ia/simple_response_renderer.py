"""
Simple response renderer - predefined questions without LLM.
Avoids LLM calls for common, deterministic data collection questions.
"""

import logging

logger = logging.getLogger(__name__)


# Predefined questions by target field
SIMPLE_QUESTIONS = {
    "tipo_servicio": "Hola, ¿qué deseas trasladar? ¿Es una mudanza, carga suelta o transporte especial?",
    "datos_ruta": "¿Cuál es el distrito de partida y llegada?",
    "lista_objetos": "¿Qué cosas vas a llevar? Puedes describirmelo o mandarme fotos. Avísame si hay algo pesado, como refri de dos puertas, ropero o aparador.",
    "incluye_personal_carga": "¿Lo necesitas solo con transporte o también con personal para cargar y descargar?",
    "modalidad_servicio": "¿Lo llevarías sin embalaje, con embalaje básico (solo lo más frágil), embalaje de muebles y artefactos, o embalaje full?",
    "requiere_desarmado": "¿Hay muebles que tengamos que desarmar y volver a armar?",
    "datos_niveles": "¿De qué piso sales y a qué piso llegas?",
    "acceso_camion": "En el origen y destino, ¿el camión puede acercarse a la puerta o hay que trasladar las cosas cierta distancia?",
    "fecha_servicio": "¿Para qué fecha lo necesitas?",
    "datos_cliente": "A nombre de quién registramos el servicio y cuál es su DNI?",
    "datos_direcciones": "Me indica la dirección exacta de partida y de llegada? Necesito calle o avenida y número, o manzana y lote.",
}

# Rephrased questions for retry attempts
REPHRASED_QUESTIONS = {
    "incluye_personal_carga": [
        "Disculpa no te entendí bien. ¿Es solo el servicio de transporte o necesitas personal para cargar y descargar?",
        "Disculpa, no me quedó claro. ¿Prefieres solo el móvil o requieres ayuda con la carga y descarga?",
        "Perdón, no entendí bien tu respuesta. ¿Quieres que vaya personal a cargar tus cosas o solo necesitas el traslado?",
    ],
    "modalidad_servicio": [
        "Disculpa no entendí. ¿Necesitas que protejamos tus cosas con embalaje o lo llevas tal cual?",
        "Perdón, no me quedó claro. ¿Quieres algún tipo de embalaje o prefieres sin embalaje?",
    ],
    "requiere_desarmado": [
        "Disculpa, no me quedó claro. ¿Hay algún mueble que necesite desarmarse para el traslado?",
        "Perdón, no entendí. ¿Tienes muebles que requieran desarmado y armado?",
    ],
    "lista_objetos": [
        "Disculpa, no capté bien. ¿Qué cosas vas a llevar? ¿Puedes describirmelo por favor?",
        "Perdón, no entendí. ¿Podrías decirme qué cosas, objetos o muebles llevarás?",
    ],
    "datos_niveles": [
        "Disculpa, no me quedó claro los pisos. ¿Me podrías repetir de qué piso a qué piso sería?",
        "Perdón, no identifiqué bien los pisos. ¿Me dices de qué piso sales y a cuál llegas?",
    ],
    "datos_ruta": [
        "Disculpa, no identifiqué bien los distritos. ¿Me repites de dónde a dónde sería el traslado?",
    ],
}


def get_simple_question(field: str, retry_count: int = 0) -> str | None:
    """
    Get predefined question for a field, with optional rephrasing on retry.

    Args:
        field: Field name
        retry_count: Number of previous attempts (0 = first attempt)

    Returns:
        Question string or None if no simple question available
    """
    # Check if there's a rephrased version
    if retry_count > 0:
        rephrased_list = REPHRASED_QUESTIONS.get(field, [])
        if retry_count <= len(rephrased_list):
            return rephrased_list[retry_count - 1]
        # Ran out of rephrasings; return original
        return SIMPLE_QUESTIONS.get(field)

    return SIMPLE_QUESTIONS.get(field)


def is_simple_response_eligible(next_target: str) -> bool:
    """Check if next target has a simple predefined question."""
    return next_target in SIMPLE_QUESTIONS


def render_simple_response(
    next_target: str,
    retry_count: int = 0,
    prefix: str = "",
) -> str | None:
    """
    Render simple response without LLM.

    Args:
        next_target: Next field to ask for
        retry_count: Number of previous unanswered attempts
        prefix: Optional prefix (e.g., customer answer before question)

    Returns:
        Complete response or None
    """
    question = get_simple_question(next_target, retry_count)
    if not question:
        return None

    if prefix:
        return f"{prefix} {question}"
    return question
