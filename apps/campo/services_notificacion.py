"""Notificar al conductor asignado a una reserva por su WhatsApp real.

Reutiliza el mismo circuito de conversación que usa la bandeja (Cliente/Lead/
Conversación vía `crear_conversacion_manual`) y el mismo envío que usa el
asesor (`send_crm_message`) — no es un canal aparte, es la misma WhatsApp
Business API de la empresa.

WhatsApp solo permite texto libre dentro de la ventana de 24h desde el último
mensaje ENTRANTE de ese número (fuera de ella solo se pueden mandar plantillas
pre-aprobadas por Meta, que esta empresa no tiene para este caso). Por eso,
si el conductor no ha escrito nada en las últimas 24h, no se intenta enviar:
se le devuelve al asesor el texto ya armado para que lo pegue a mano en
WhatsApp Web (mismo criterio que ChatComposer.vue's pendingTemplate, pero acá
con el tiempo real transcurrido en vez de "alguna vez escribió", porque este
envío es automático y sin nadie mirando — mejor no intentarlo que arriesgar
un rechazo silencioso de WhatsApp).
"""
from datetime import timedelta

from django.utils import timezone

VENTANA_24H = timedelta(hours=24)


def _formato_mensaje(programacion):
    s = programacion.servicio
    lineas = [
        f"📋 Nueva asignación — {s.codigo}",
        f"Cliente: {s.cliente.nombre if s.cliente else '—'}",
        f"Fecha: {programacion.fecha.strftime('%d/%m/%Y')} {programacion.hora_inicio.strftime('%H:%M')}",
    ]
    if s.distrito_origen or s.distrito_destino:
        lineas.append(f"Ruta: {s.distrito_origen or '?'} → {s.distrito_destino or '?'}")
    if s.direccion_origen:
        piso = f" (Piso {s.piso_origen})" if s.piso_origen else ""
        lineas.append(f"Origen: {s.direccion_origen}{piso}")
    if s.direccion_destino:
        piso = f" (Piso {s.piso_destino})" if s.piso_destino else ""
        lineas.append(f"Destino: {s.direccion_destino}{piso}")
    if s.detalle_carga:
        lineas.append(f"Carga: {s.detalle_carga}")
    elif s.lista_objetos:
        lineas.append(f"Carga: {s.lista_objetos}")
    lineas.append(f"Monto: S/ {programacion.monto}")
    if s.observaciones:
        lineas.append(f"Notas: {s.observaciones}")
    return "\n".join(lineas)


def notificar_conductor_asignacion(programacion, actor):
    """Intenta avisarle al conductor por WhatsApp. Devuelve siempre el texto
    armado (se use o no) para que el asesor lo pueda copiar a mano si hace falta.

    Returns:
        {"enviado": bool, "mensaje": str, "motivo": str | None}
        `motivo` explica por qué NO se envió (None si se envió bien).
    """
    from apps.whatsapp.domain import crear_conversacion_manual

    conductor = programacion.conductor
    mensaje = _formato_mensaje(programacion)
    telefono = (conductor.telefono or "").strip()
    if not telefono:
        return {"enviado": False, "mensaje": mensaje, "motivo": "El conductor no tiene teléfono registrado."}

    try:
        conversacion = crear_conversacion_manual(telefono, actor, nombre=conductor.nombre)
    except Exception:
        return {
            "enviado": False, "mensaje": mensaje,
            "motivo": "No se pudo preparar la conversación de WhatsApp del conductor.",
        }

    dentro_de_ventana = (
        conversacion.ultimo_mensaje_cliente is not None
        and timezone.now() - conversacion.ultimo_mensaje_cliente < VENTANA_24H
    )
    if not dentro_de_ventana:
        return {
            "enviado": False, "mensaje": mensaje,
            "motivo": "Fuera de la ventana de 24h de WhatsApp — envíalo a mano por WhatsApp Web.",
        }

    from apps.whatsapp.services import send_crm_message
    resultado = send_crm_message(conversacion, actor, mensaje)
    if not resultado["success"]:
        return {
            "enviado": False, "mensaje": mensaje,
            "motivo": resultado["error_detail"] or "WhatsApp rechazó el envío — mándalo a mano por WhatsApp Web.",
        }
    return {"enviado": True, "mensaje": mensaje, "motivo": None}
