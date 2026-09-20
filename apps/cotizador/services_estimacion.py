"""Estimación de peso/volumen de una carga a partir de su descripción libre
y, opcionalmente, fotos — cuando el cliente no escribió ningún número
explícito (el caso más común — "un juego de sala" en vez de "500 kg y 2
m3"). Sin esto, el paso "Precio" y la recomendación de modalidad
(Compartido/Exclusivo) no tienen con qué trabajar para la mayoría de las
descripciones reales.

Es una extracción de un solo turno (texto [+ fotos] entra, JSON estructurado
sale), NO un agente — mismo patrón que ya usa `apps/ia/delta_extractor.py`
con `build_provider("extraction").generate_structured(...)`. Nunca lanza: si
la IA no está configurada, falla o no puede estimar nada, devuelve None y el
llamador cae al aviso "no pudimos calcular el precio".
"""
import base64
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.ia.providers import AIProviderError, build_provider

logger = logging.getLogger(__name__)

PROMPT_SISTEMA = (
    "Eres un experto en logística de mudanzas y carga en Perú. Te dan una "
    "descripción libre de lo que alguien quiere transportar (puede nombrar "
    "objetos comunes sin ningún número, p. ej. 'un juego de sala', '40 cajas "
    "de ropa', 'una moto usada') y, a veces, fotos de la carga — y estimás "
    "el peso total aproximado (en kg) y el volumen total aproximado (en m3) "
    "que ocuparía en un camión, usando tu conocimiento general de cuánto "
    "pesan y ocupan objetos típicos. Si hay fotos, son la evidencia más "
    "confiable para el volumen (contá bultos, compará tamaños visibles) — "
    "úsalas por encima del texto si se contradicen.\n"
    "Reglas:\n"
    "- Si la descripción ya trae un número explícito de peso o volumen, "
    "usalo tal cual en vez de estimar.\n"
    "- Si ni el texto ni las fotos alcanzan para estimar nada razonable: "
    "devolvé null en peso_kg y volumen_m3, confianza 'baja', y proponé en "
    "'pregunta_sugerida' UNA sola pregunta que el propio cliente (sin "
    "conocimientos técnicos) pueda responder con un número simple — nunca "
    "le pidas kg ni m3 directamente. Elegí la pregunta según el tipo de "
    "carga: cantidad de cajas/bultos, largo aproximado en metros de lo más "
    "grande, cantidad de ambientes de la casa, etc. — lo que más ayude para "
    "ESA carga puntual. 'unidad' es la unidad de la respuesta esperada "
    "('cajas', 'metros', 'ambientes', etc.).\n"
    "- Si sí pudiste estimar algo (aunque sea con confianza 'media'), no "
    "pongas pregunta_sugerida.\n"
    "- confianza 'alta' = objetos conocidos y concretos (texto y/o fotos "
    "claras); 'media' = estimación razonable pero con rango amplio; 'baja' "
    "= no se pudo estimar nada útil."
)

MAX_FOTOS = 5


class PreguntaSugerida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str
    unidad: str


class EstimacionCarga(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peso_kg: float | None = Field(default=None, ge=0)
    volumen_m3: float | None = Field(default=None, ge=0)
    confianza: Literal["alta", "media", "baja"]
    pregunta_sugerida: PreguntaSugerida | None = Field(default=None)


def _bloques_fotos(fotos):
    """[{"type": "input_image", "image_url": "data:...;base64,..."}] — mismo
    patrón que `apps/ia/image_analyzer.py::analyze_moving_image` (MEDIA_ROOT
    es local sin URL pública, así que siempre hay que leer y codificar)."""
    bloques = []
    for archivo in fotos[:MAX_FOTOS]:
        try:
            archivo.seek(0)
            encoded = base64.b64encode(archivo.read()).decode("ascii")
        except Exception:
            continue
        mime = getattr(archivo, "content_type", None) or "image/jpeg"
        bloques.append({"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"})
    return bloques


def estimar_carga_por_ia(descripcion, fotos=None, *, provider_name=None):
    """Devuelve {"weightKg", "volumeM3", "confidence", "suggestedQuestion"}
    o None (solo en error real de proveedor/parseo). Nunca lanza.

    `suggestedQuestion` ({"text", "unit"} o None) es la pregunta de
    aclaración en lenguaje simple que arma la propia IA cuando ni el texto
    ni las fotos alcanzan — nunca pide kg/m3 directos (ver PROMPT_SISTEMA).
    """
    texto = (descripcion or "").strip()
    fotos = fotos or []
    if not texto and not fotos:
        return None

    # Con fotos, forzamos OpenAI explícito: es el único proveedor probado en
    # este repo para imágenes (ver apps/ia/image_analyzer.py). El soporte de
    # visión de DeepSeek es contra su endpoint /chat/completions, no
    # confirmado contra la superficie "Responses" que usa este módulo.
    if fotos:
        provider_name = "openai"

    contenido = [{"type": "input_text", "text": texto or "(sin descripción de texto, ver fotos)"}]
    contenido.extend(_bloques_fotos(fotos))

    try:
        provider = build_provider("extraction", provider_name=provider_name)
        result = provider.generate_structured(
            [
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": contenido if fotos else texto},
            ],
            schema_model=EstimacionCarga,
            purpose="estimar_carga",
        )
        parsed = EstimacionCarga.model_validate_json(result.text)
    except (AIProviderError, ValidationError) as e:
        logger.warning("[EstimacionCarga] Estimación falló: %s", e)
        return None
    except Exception as e:  # nunca romper el flujo de publicación por esto
        logger.warning("[EstimacionCarga] Error inesperado: %s", e)
        return None

    pregunta = None
    if parsed.confianza == "baja" and parsed.peso_kg is None and parsed.volumen_m3 is None:
        if parsed.pregunta_sugerida:
            pregunta = {"text": parsed.pregunta_sugerida.texto, "unit": parsed.pregunta_sugerida.unidad}

    return {
        "weightKg": parsed.peso_kg,
        "volumeM3": parsed.volumen_m3,
        "confidence": parsed.confianza,
        "suggestedQuestion": pregunta,
    }
