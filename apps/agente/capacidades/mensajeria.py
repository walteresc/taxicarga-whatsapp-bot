"""Capacidades de mensajería saliente.

NO tocan la lógica del bot en vivo ni interceptan mensajes entrantes: solo
mandan un mensaje puntual por el canal de salida que ya existe, o encolan una
revisión de cotización. Ambas son `escritura_critica` — nunca se auto-invocan.
"""
from apps.agente.errores import ArgInvalido, NoEncontrado
from apps.agente.registro import EFECTO_CRITICO, capacidad

from . import _alcance


@capacidad("enviar_whatsapp", perfiles=["asesor", "sistema"], efecto=EFECTO_CRITICO)
def enviar_whatsapp(principal, carga_codigo, texto):
    """Envía un mensaje de WhatsApp al contacto de una carga."""
    from apps.whatsapp_bot_v4.services.ycloud_webhook_service import send_via_ycloud

    texto = (texto or "").strip()
    if not texto:
        raise ArgInvalido("El mensaje está vacío.")
    lead = _alcance.carga_para(principal, carga_codigo)
    telefono = (getattr(lead.cliente, "telefono", "") or "").strip()
    if not telefono or telefono.startswith("YCID:"):
        raise NoEncontrado("La carga no tiene un teléfono de WhatsApp utilizable.")
    send_via_ycloud(telefono, texto)
    return {"enviado_a": telefono, "_lead": lead}


@capacidad("encolar_revision_whatsapp", perfiles=["asesor", "sistema"], efecto=EFECTO_CRITICO)
def encolar_revision_whatsapp(principal, cotizacion_codigo):
    """Encola el envío por WhatsApp de la última revisión de una cotización."""
    from apps.cotizador.delivery import queue_revision_whatsapp

    cot = _alcance.cotizacion_para(principal, cotizacion_codigo)
    revision = cot.revisiones.order_by("-numero").first()
    if revision is None:
        raise NoEncontrado("La cotización no tiene revisiones.")
    queue_revision_whatsapp(revision.id, actor=principal.user)
    return {"revision": revision.numero, "cotizacion": cot.codigo, "_lead": cot.lead}
