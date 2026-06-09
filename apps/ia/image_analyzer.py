import base64
import json
import logging

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)


IMAGE_PROMPT = """
Analiza esta foto para cotizar un traslado o mudanza. Devuelve solamente JSON:
{
  "objetos": ["objeto visible con cantidad aproximada"],
  "objetos_pesados": ["objetos que requieren cuidado o esfuerzo especial"],
  "resumen": "inventario breve y natural en espanol"
}
Describe solo lo visible. No inventes objetos ocultos, dimensiones, peso, pisos,
direcciones ni servicios. Distingue, cuando sea visible, escritorio, silla,
computadora/CPU, monitor, refrigeradora, ropero, comoda, aparador, cajas y muebles.
"""


def analyze_moving_image(evidence):
    if not settings.OPENAI_API_KEY or not evidence or not evidence.archivo:
        return None

    try:
        with evidence.archivo.open("rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("ascii")
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.responses.create(
            model=settings.OPENAI_MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": IMAGE_PROMPT},
                        {
                            "type": "input_image",
                            "image_url": f"data:{evidence.mime_type};base64,{encoded}",
                        },
                    ],
                }
            ],
        )
        result = _parse_json(response.output_text)
        if not result.get("objetos"):
            return None
        return result
    except Exception:
        logger.exception("No se pudo analizar la imagen de WhatsApp.")
        return None


def _parse_json(value):
    text = (value or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    data = json.loads(text)
    return {
        "objetos": [str(item).strip() for item in data.get("objetos", []) if str(item).strip()],
        "objetos_pesados": [
            str(item).strip()
            for item in data.get("objetos_pesados", [])
            if str(item).strip()
        ],
        "resumen": str(data.get("resumen", "")).strip(),
    }
