from .models import EjemploConversacion


TAG_KEYWORDS = {
    "saludo": ["hola", "buenos dias", "buenas tardes"],
    "ruta": ["origen", "destino", "distrito", "zona"],
    "objetos": ["lista", "foto", "cama", "refrigeradora", "mueble", "cajas"],
    "acceso": ["piso", "ascensor", "escalera", "puerta", "camion"],
    "embalaje": ["embal", "proteger", "forrar"],
    "desarmado": ["desarm", "armado", "armar"],
    "precio": ["precio", "costo", "cotiza", "soles", "s/"],
    "reserva": ["reserv", "dni", "direccion", "fecha", "hora"],
    "seguimiento": ["seguimos", "confirma", "decidio", "decidió"],
}


def conversation_examples_for(message, fallback_question, limit=3):
    tags = _infer_tags(f"{message}\n{fallback_question}")
    candidates = EjemploConversacion.objects.filter(
        fuente="whatsapp_export",
        requiere_revision=False,
    ).order_by("-fecha_importacion")[:250]
    scored = []
    for example in candidates:
        overlap = len(tags & set(example.etiquetas))
        if overlap:
            scored.append((overlap, example))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [example for _score, example in scored[:limit]]


def format_examples_for_prompt(examples):
    if not examples:
        return ""
    lines = ["Ejemplos anonimizados de conversaciones reales similares:"]
    for example in examples:
        lines.append(f"Cliente: {example.mensaje_cliente}")
        lines.append(f"Asesor: {example.respuesta_negocio}")
    return "\n".join(lines)


def _infer_tags(text):
    lowered = text.lower()
    return {
        tag
        for tag, keywords in TAG_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    }
