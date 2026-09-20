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
    "devolvé 0 en peso_kg y volumen_m3 (0 significa 'no se pudo estimar', "
    "nunca es un valor real), confianza 'baja', y completá "
    "'pregunta_sugerida' con UNA sola pregunta que el propio cliente (sin "
    "conocimientos técnicos) pueda responder con un número simple — nunca "
    "le pidas kg ni m3 directamente. Elegí la pregunta según el tipo de "
    "carga: cantidad de cajas/bultos, largo aproximado en metros de lo más "
    "grande, cantidad de ambientes de la casa, etc. — lo que más ayude para "
    "ESA carga puntual. 'unidad' es la unidad de la respuesta esperada "
    "('cajas', 'metros', 'ambientes', etc.).\n"
    "- Si sí pudiste estimar algo (aunque sea con confianza 'media'), dejá "
    "pregunta_sugerida con texto y unidad vacíos (\"\").\n"
    "- confianza 'alta' = objetos conocidos y concretos (texto y/o fotos "
    "claras); 'media' = estimación razonable pero con rango amplio; 'baja' "
    "= no se pudo estimar nada útil."
)

MAX_FOTOS = 5

# Los schemas de acá abajo evitan a propósito Optional/`| None` (que Pydantic
# traduce a `anyOf` en JSON Schema): DeepSeek rechaza ese `anyOf` en modo
# estructurado ("Invalid json schema: field `anyOf`: missing field `type`"),
# tanto para tipos simples como para un objeto anidado opcional — confirmado
# en vivo contra su API. En vez de eso, "sin dato" se representa con
# centinelas (0 = no se pudo estimar; texto/unidad vacíos = sin pregunta) y
# TODOS los campos son siempre requeridos — funciona igual en OpenAI y
# DeepSeek, sin ramas de schema por proveedor.


class PreguntaSugerida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str = ""
    unidad: str = ""


class EstimacionCarga(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peso_kg: float = Field(default=0, ge=0)
    volumen_m3: float = Field(default=0, ge=0)
    confianza: Literal["alta", "media", "baja"]
    pregunta_sugerida: PreguntaSugerida = Field(default_factory=PreguntaSugerida)


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

    # 0 es el centinela de "no se pudo estimar" (ver PROMPT_SISTEMA) — nunca
    # un peso/volumen real (nada pesa u ocupa 0).
    peso = parsed.peso_kg or None
    volumen = parsed.volumen_m3 or None

    pregunta = None
    if peso is None and volumen is None and parsed.pregunta_sugerida.texto:
        pregunta = {"text": parsed.pregunta_sugerida.texto, "unit": parsed.pregunta_sugerida.unidad}

    return {
        "weightKg": peso,
        "volumeM3": volumen,
        "confidence": parsed.confianza,
        "suggestedQuestion": pregunta,
    }
