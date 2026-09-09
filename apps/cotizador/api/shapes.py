"""Serialización ES→EN del pipeline comercial. Único sitio del módulo donde se
da forma a la respuesta de la API v2 (ver docs/PATRON-API-VUE.md).

Todo lo de aquí es de solo lectura y compuesto (no CRUD de un modelo), por eso
son funciones que devuelven dicts con claves inglesas, no serializers DRF.
"""
from apps.cotizador.models import CotizacionComercial, RevisionCotizacion


def _d(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


def lead_summary(lead):
    """Resumen del servicio, común a todas las pantallas del pipeline."""
    if lead is None:
        return None
    cli = lead.cliente
    return {
        "leadId": lead.id,
        "customer": {
            "id": cli.id if cli else None,
            "name": (cli.profile_name if cli else "") or (cli.contact_phone if cli else ""),
            "phone": cli.contact_phone if cli else "",
        },
        "type": lead.tipo_servicio or None,
        "origin": lead.distrito_origen or None,
        "destination": lead.distrito_destino or None,
        "addressOrigin": lead.direccion_origen or None,
        "addressDestination": lead.direccion_destino or None,
        "floorOrigin": lead.piso_origen,
        "floorDestination": lead.piso_destino,
        "elevatorOrigin": lead.ascensor_origen,
        "elevatorDestination": lead.ascensor_destino,
        "items": lead.lista_objetos or None,
        "heavyItems": lead.objetos_pesados or None,
        "serviceDate": _d(lead.fecha_servicio),
        "schedule": lead.horario_servicio or None,
        "weightKg": float(lead.peso_carga_kg) if lead.peso_carga_kg is not None else None,
        "volumeM3": float(lead.volumen_carga_m3) if lead.volumen_carga_m3 is not None else None,
        "isInterprovincial": lead.es_interprovincial,
        "priority": lead.prioridad,
    }


def texto_servicio(lead, conv=None):
    """Texto plano del servicio, para que el asesor lo mande a un conductor por
    WhatsApp (o lo copie a mano). Mismo origen de datos que el panel: Lead +
    datos_extraidos como respaldo."""
    ex = (conv.datos_extraidos or {}) if conv is not None else {}

    def t(attr, exkey=None):
        v = getattr(lead, attr, None)
        if v not in (None, ""):
            return v
        return ex.get(exkey or attr) or None

    def _piso(v):
        if v in (None, ""):
            return ""
        try:
            n = int(v)
        except (TypeError, ValueError):
            return f" · Piso {v}"
        if n == 0:
            return " · Planta baja"
        return f" · Sótano {abs(n)}" if n < 0 else f" · Piso {n}"

    L = []
    tipo = t("tipo_servicio")
    L.append(f"📦 Servicio{f' — {str(tipo).capitalize()}' if tipo else ''}")
    fecha = lead.fecha_servicio.strftime("%d/%m/%Y") if lead.fecha_servicio else (
        ex.get("fecha_servicio") or ex.get("fecha_texto") or "Por confirmar")
    L.append(f"Fecha: {fecha}")
    if t("horario_servicio"):
        L.append(f"Horario: {t('horario_servicio')}")

    o_addr = t("direccion_origen") or t("distrito_origen", "distrito_origen")
    if o_addr:
        piso = t("piso_origen")
        asc = lead.ascensor_origen
        extra = "".join([
            _piso(piso),
            " · con ascensor" if asc is True else " · sin ascensor" if asc is False else "",
        ])
        L.append(f"Origen: {o_addr}{extra}")
    d_addr = t("direccion_destino") or t("distrito_destino", "distrito_destino")
    if d_addr:
        piso = t("piso_destino")
        asc = lead.ascensor_destino
        extra = "".join([
            _piso(piso),
            " · con ascensor" if asc is True else " · sin ascensor" if asc is False else "",
        ])
        L.append(f"Destino: {d_addr}{extra}")

    if t("lista_objetos"):
        L.append(f"Carga: {t('lista_objetos')}")
    if t("objetos_pesados"):
        L.append(f"Objetos pesados: {t('objetos_pesados')}")
    peso, vol = t("peso_carga_kg"), t("volumen_carga_m3")
    if peso or vol:
        L.append("Peso/Volumen: " + " · ".join(filter(None, [
            f"{peso} kg" if peso else "", f"{vol} m³" if vol else ""])))
    if lead.precio_cotizado is not None:
        L.append(f"Precio: S/ {lead.precio_cotizado}")
    if lead.persona_contacto or lead.telefono_contacto:
        L.append("Contacto en sitio: " + " ".join(filter(None, [
            lead.persona_contacto, lead.telefono_contacto])))
    return "\n".join(L)


def potential_item(lead):
    """Fila de 'Potenciales' — lead que sigue conversando, sin escalar aún."""
    conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
    origin_dest = (
        f"{lead.distrito_origen or '?'} → {lead.distrito_destino or '?'}"
        if (lead.distrito_origen or lead.distrito_destino) else None
    )
    return {
        "id": lead.id,
        "leadId": lead.id,
        "customerName": (lead.cliente.profile_name if lead.cliente else "") or "—",
        "route": origin_dest,
        "type": lead.tipo_servicio or None,
        "informationPct": conv.porcentaje_informacion if conv else 0,
        "isInterprovincial": lead.es_interprovincial,
        "priority": lead.prioridad,
        "createdAt": _d(lead.fecha_creacion),
        "conversationId": conv.id if conv else None,
        "seen": _visto("potentials", lead.id),
    }


def review_item(solicitud):
    """Fila de 'Para revisión'."""
    lead = solicitud.lead
    return {
        "id": solicitud.id,
        "leadId": lead.id,
        "customerName": (lead.cliente.profile_name if lead.cliente else "") or "—",
        "route": f"{lead.distrito_origen or '?'} → {lead.distrito_destino or '?'}",
        "reason": solicitud.motivo or "Requiere revisión",
        "isInterprovincial": lead.es_interprovincial,
        "priority": solicitud.prioridad,
        "assignedTo": _user(solicitud.asignada_a),
        "createdAt": _d(solicitud.creada_en),
        "conversationId": solicitud.conversacion_id,
        "seen": _visto("review", lead.id),
    }


def _user(u):
    if not u:
        return None
    return {"id": u.id, "name": u.get_full_name() or u.username}


def _visto(etapa, lead_id):
    """True si alguien ya abrió el detalle de este lead estando en `etapa`."""
    if not lead_id:
        return True
    from apps.cotizador.models import PipelineVisto
    return PipelineVisto.objects.filter(etapa=etapa, lead_id=lead_id).exists()


def _quien_descarto(lead):
    """Best-effort: quién descartó el lead. Primero la traza de `descartar_lead`
    en nota_interna, si no el vendedor asignado."""
    import re
    for linea in reversed((lead.nota_interna or "").splitlines()):
        m = re.search(r"\]\s*([^:]+):\s*descartada", linea)
        if m:
            return m.group(1).strip()
    u = _user(lead.vendedor_asignado)
    return u["name"] if u else None


def lost_item(lead):
    """Fila de 'Perdidos' — lead descartado / marcado perdido."""
    conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
    motivo = lead.get_motivo_perdida_display() if lead.motivo_perdida else ""
    detalle = (lead.motivo_perdida_detalle or "").strip()
    if detalle and detalle.lower() != (motivo or "").lower():
        motivo = f"{motivo} — {detalle}" if motivo else detalle
    return {
        "id": lead.id,
        "leadId": lead.id,
        "customerName": (lead.cliente.profile_name if lead.cliente else "") or "—",
        "route": f"{lead.distrito_origen or '?'} → {lead.distrito_destino or '?'}",
        "reason": motivo or "Sin motivo registrado",
        "lostBy": _quien_descarto(lead),
        "lostAt": _d(lead.fecha_cierre),
        "isInterprovincial": lead.es_interprovincial,
        "conversationId": conv.id if conv else None,
        "createdAt": _d(lead.fecha_creacion),
    }


def _data_source(conv):
    """Quién recabó los datos del servicio en la conversación: bot, asesor o ambos."""
    if conv is None:
        return None
    origenes = set(
        conv.mensajes.filter(direccion="saliente")
        .order_by().values_list("origen", flat=True).distinct()
    )
    bot, asesor = "bot" in origenes, "asesor" in origenes
    if bot and asesor:
        return "ambos"
    if asesor:
        return "asesor"
    return "bot"


# --------------------------------------------------------------------------- #
#  Por cotizar
# --------------------------------------------------------------------------- #

def quote_request_item(solicitud):
    lead = solicitud.lead
    conv = solicitud.conversacion
    return {
        "id": solicitud.id,
        "leadId": lead.id,
        "customerName": (lead.cliente.profile_name if lead.cliente else "") or "—",
        "route": f"{lead.distrito_origen or '?'} → {lead.distrito_destino or '?'}",
        "serviceDate": _d(lead.fecha_servicio),
        "reason": solicitud.motivo or "",
        "isInterprovincial": lead.es_interprovincial,
        "priority": solicitud.prioridad,
        "assignedTo": _user(solicitud.asignada_a),
        "informationPct": conv.porcentaje_informacion if conv else 0,
        "dataSource": _data_source(conv),
        "conversationId": conv.id if conv else None,
        "createdAt": _d(solicitud.creada_en),
        "hasDraft": solicitud.cotizaciones.filter(estado="borrador").exists(),
        "seen": _visto("quoting", lead.id),
    }


def quote_request_detail(solicitud, *, technical=None, frequent_route=None):
    lead = solicitud.lead
    draft = solicitud.cotizaciones.filter(estado="borrador").order_by("-creada_en").first()
    latest = draft.revisiones.order_by("-numero").first() if draft else None
    out = {
        "id": solicitud.id,
        "service": lead_summary(lead),
        "assignedTo": _user(solicitud.asignada_a),
        "isInterprovincial": lead.es_interprovincial,
        "reason": solicitud.motivo or "",
        "suggested": None,
        "frequentRoute": frequent_route,
        "draft": None,
    }
    if technical is not None:
        out["suggested"] = {
            "min": float(technical.precio_min),
            "recommended": float(technical.precio_recomendado),
            "max": float(technical.precio_max),
            "similarServices": technical.servicios_similares_encontrados,
            "explanation": technical.explicacion,
        }
    if latest is not None:
        out["draft"] = {
            "code": draft.codigo,
            "revision": latest.numero,
            "price": float(latest.precio_final),
            "cost": float(latest.costo_estimado) if latest.costo_estimado is not None else None,
            "conditions": latest.condiciones,
            "validityDays": latest.vigencia_dias,
            "internalNote": latest.observacion_interna,
            "whatsappMessage": latest.mensaje_whatsapp,
        }
    return out


# --------------------------------------------------------------------------- #
#  Cotizaciones
# --------------------------------------------------------------------------- #

_QUOTE_STATE_EN = {
    "borrador": "draft", "enviada": "sent", "entregada": "delivered",
    "en_negociacion": "negotiating", "aceptada": "accepted", "rechazada": "rejected",
    "vencida": "expired", "cancelada": "cancelled",
}
QUOTE_STATE_ES = {v: k for k, v in _QUOTE_STATE_EN.items()}


def quote_item(cotizacion):
    lead = cotizacion.lead
    revs = list(cotizacion.revisiones.order_by("-numero"))
    last = revs[0] if revs else None
    conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
    return {
        "id": cotizacion.id,
        "code": cotizacion.codigo,
        "leadId": lead.id,
        "conversationId": conv.id if conv else None,
        "isInterprovincial": lead.es_interprovincial,
        "customerName": (lead.cliente.profile_name if lead.cliente else "") or "—",
        "route": f"{lead.distrito_origen or '?'} → {lead.distrito_destino or '?'}",
        "state": _QUOTE_STATE_EN.get(cotizacion.estado, cotizacion.estado),
        "origin": cotizacion.origen,
        "advisor": _user(cotizacion.asesor),
        "currentPrice": float(last.precio_final) if last else None,
        "clientPrice": float(cotizacion.precio_cliente) if cotizacion.precio_cliente is not None else None,
        "agreedPrice": float(cotizacion.precio_acordado) if cotizacion.precio_acordado is not None else None,
        "revisionCount": len(revs),
        "createdAt": _d(cotizacion.creada_en),
        "updatedAt": _d(cotizacion.actualizada_en),
        "hasBooking": hasattr(lead, "servicio_generado") and lead.servicio_generado is not None,
        "outsourced": _quote_outsourced(lead),
        "seen": _visto("quotes", lead.id),
    }


def _quote_outsourced(lead):
    """(bool, código de publicación) — si la carga ya fue derivada a tercerización."""
    servicio = getattr(lead, "servicio_generado", None)
    if not servicio:
        return None
    pub = servicio.publicaciones_tercerizacion.exclude(
        estado__in=("cancelada", "vencida"),
    ).order_by("-creado_en").first()
    if not pub:
        return None
    return {"code": pub.codigo, "state": pub.estado, "priceMode": pub.modo_precio}


def quote_detail(cotizacion):
    out = quote_item(cotizacion)
    out["service"] = lead_summary(cotizacion.lead)
    out["revisions"] = [
        {
            "number": r.numero,
            "price": float(r.precio_final),
            "conditions": r.condiciones,
            "validityDays": r.vigencia_dias,
            "sent": r.enviada,
            "sentAt": _d(r.enviada_en),
            "createdAt": _d(r.creada_en),
            "whatsappMessage": r.mensaje_whatsapp,
        }
        for r in cotizacion.revisiones.order_by("-numero")
    ]
    return out


# --------------------------------------------------------------------------- #
#  Reservas
# --------------------------------------------------------------------------- #

_BOOKING_STATE_EN = {
    "pendiente": "pending", "programado": "scheduled", "asignado": "assigned",
    "en_ruta": "on_route", "finalizado": "completed", "cancelado": "cancelled",
}
BOOKING_STATE_ES = {v: k for k, v in _BOOKING_STATE_EN.items()}

_PAYMENT_STATE_EN = {
    "pagado": "paid", "amortizado": "partial", "pendiente": "pending", "sin_precio": "no_price",
}


def _booking_assignment(servicio):
    """(assignmentState, executor) — quién ejecuta y en qué punto está.
      sin_asignar → nadie todavía
      publicado   → OFERTA abierta en el grupo de transportistas
      asignado    → hay una programación con conductor propio o con transportista
    """
    prog = (servicio.programaciones.exclude(estado_operativo="cancelado")
            .select_related("conductor", "transportista", "transportista_vehiculo").first())
    if prog:
        if prog.conductor_id:
            return "asignado", prog.conductor.nombre
        if prog.transportista_vehiculo_id:
            return "asignado", (
                prog.conductor_externo
                or (prog.transportista.nombre if prog.transportista_id else None)
                or prog.transportista_vehiculo.placa
            )
    if servicio.publicaciones_tercerizacion.filter(estado="abierta").exists():
        return "publicado", None
    return "sin_asignar", None


def booking_item(servicio):
    lead = servicio.lead_origen
    conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first() if lead else None
    from apps.servicios.utils import parse_horario
    from apps.servicios.models import ConfiguracionOperaciones
    hora = parse_horario(servicio.horario_servicio)
    assignment, executor = _booking_assignment(servicio)
    return {
        "id": servicio.id,
        "code": servicio.codigo,
        "leadId": lead.id if lead else None,
        "conversationId": conv.id if conv else None,
        "seen": _visto("bookings", lead.id if lead else None),
        "customerName": (servicio.cliente.profile_name if servicio.cliente else "") or "—",
        "route": f"{servicio.distrito_origen or '?'} → {servicio.distrito_destino or '?'}",
        "type": servicio.tipo_servicio or None,
        "serviceDate": _d(servicio.fecha_servicio),
        "serviceTime": hora.strftime("%H:%M") if hora else None,
        "state": _BOOKING_STATE_EN.get(servicio.estado, servicio.estado),
        "price": float(servicio.precio) if servicio.precio is not None else None,
        "paid": float(servicio.total_pagado),
        "balance": float(servicio.saldo_pendiente),
        "paymentState": _PAYMENT_STATE_EN.get(servicio.estado_pago, servicio.estado_pago),
        "isInterprovincial": servicio.es_interprovincial,
        "hasTeam": servicio.programaciones.exists(),
        "executionMode": servicio.modalidad_ejecucion,
        "assignmentState": assignment,
        "executor": executor,
        "isNight": (hora is not None and ConfiguracionOperaciones.get_solo().es_nocturno(hora)),
        "advisor": _user(servicio.asesor),
        "createdAt": _d(servicio.fecha_creacion),
    }


def booking_detail(servicio):
    out = booking_item(servicio)
    out["service"] = lead_summary(servicio.lead_origen) if servicio.lead_origen else None
    prog = (servicio.programaciones.exclude(estado_operativo="cancelado")
            .select_related("vehiculo", "transportista_vehiculo").first())
    out["assignmentId"] = prog.id if prog else None
    out["assignedVehicleId"] = prog.vehiculo_id if prog else None
    out["assignedCarrierVehicleId"] = prog.transportista_vehiculo_id if prog else None
    out["assignedPlate"] = (
        (prog.vehiculo.placa if prog.vehiculo_id else prog.transportista_vehiculo.placa)
        if prog and (prog.vehiculo_id or prog.transportista_vehiculo_id) else None
    )
    out["assignedStart"] = prog.hora_inicio.strftime("%H:%M") if prog and prog.hora_inicio else None
    out["assignedEnd"] = prog.hora_fin.strftime("%H:%M") if prog and prog.hora_fin else None
    out["addressOrigin"] = servicio.direccion_origen or None
    out["addressDestination"] = servicio.direccion_destino or None
    out["schedule"] = servicio.horario_servicio or None
    out["items"] = servicio.lista_objetos or None
    out["notes"] = servicio.observaciones or None
    out["payments"] = [
        {
            "id": p.id,
            "concept": p.concepto,
            "method": p.metodo_pago,
            "amount": float(p.monto),
            "paidAt": _d(p.fecha_pago),
            "note": p.observaciones,
        }
        for p in servicio.pagos.order_by("-fecha_pago")
    ]
    return out
