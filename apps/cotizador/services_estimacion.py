"""Estimación de peso/volumen de una carga a partir de su descripción libre,
cuando el cliente no escribió ningún número explícito (el caso más común —
"un juego de sala" en vez de "500 kg y 2 m3"). Sin esto, el paso "Precio" y
la recomendación de modalidad (Compartido/Exclusivo) no tienen con qué
trabajar para la mayoría de las descripciones reales.

Es una extracción de un solo turno (texto entra, JSON estructurado sale),
NO un agente — mismo patrón que ya usa `apps/ia/delta_extractor.py` con
`build_provider("extraction").generate_structured(...)`. Nunca lanza: si la
IA no está configurada, falla o no puede estimar nada, devuelve None y el
llamador cae al aviso "no pudimos calcular el precio".
"""
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.ia.providers import AIProviderError, build_provider

logger = logging.getLogger(__name__)

PROMPT_SISTEMA = (
    "Eres un experto en logística de mudanzas y carga en Perú. Te dan una "
    "descripción libre de lo que alguien quiere transportar (puede nombrar "
    "objetos comunes sin ningún número, p. ej. 'un juego de sala', '40 cajas "
    "de ropa', 'una moto usada') y estimás el peso total aproximado (en kg) "
    "y el volumen total aproximado (en m3) que ocuparía en un camión, usando "
    "tu conocimiento general de cuánto pesan y ocupan objetos típicos.\n"
    "Reglas:\n"
    "- Si la descripción ya trae un número explícito de peso o volumen, "
    "usalo tal cual en vez de estimar.\n"
    "- Si la descripción es demasiado vaga para estimar nada razonable "
    "(p. ej. 'cosas varias', 'un poco de todo'), devolvé null en ambos "
    "campos y confianza 'baja'.\n"
    "- confianza 'alta' = objetos conocidos y concretos; 'media' = estimación "
    "razonable pero con rango amplio; 'baja' = no se pudo estimar nada útil."
)


class EstimacionCarga(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peso_kg: float | None = Field(default=None, ge=0)
    volumen_m3: float | None = Field(default=None, ge=0)
    confianza: Literal["alta", "media", "baja"]


def estimar_carga_por_ia(descripcion, *, provider_name=None):
    """Devuelve {"weightKg", "volumeM3", "confidence"} o None. Nunca lanza."""
    texto = (descripcion or "").strip()
    if not texto:
        return None
    try:
        provider = build_provider("extraction", provider_name=provider_name)
        result = provider.generate_structured(
            [
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": texto},
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

    if parsed.confianza == "baja" and parsed.peso_kg is None and parsed.volumen_m3 is None:
        return None

    return {
        "weightKg": parsed.peso_kg,
        "volumeM3": parsed.volumen_m3,
        "confidence": parsed.confianza,
    }
