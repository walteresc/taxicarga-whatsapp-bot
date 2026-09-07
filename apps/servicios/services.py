from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.cotizador.models import RevisionCotizacion
from apps.ia.conversation_policy import booking_missing_fields, effective_quote_values
from apps.leads.route import route_for_lead
from apps.leads.cargo import effective_load_detail

from .models import Servicio, ServicioUbicacion, SERVICIO_PENDIENTE


@transaction.atomic
def crear_servicio_desde_lead(lead, usuario=None, revision=None, *, require_accepted_revision=False):
    lead = type(lead).objects.select_for_update().select_related("cliente").get(pk=lead.pk)
    existing = Servicio.objects.select_for_update().filter(lead_origen=lead).first()
    if existing:
        return existing, False
    if booking_missing_fields(lead):
        raise ValidationError("La reserva no tiene todos los datos obligatorios.")
    if revision is None:
        revision = (
            RevisionCotizacion.objects.select_related("cotizacion")
            .filter(cotizacion__lead=lead, cotizacion__estado="aceptada", enviada=True)
            .order_by("-cotizacion__actualizada_en", "-numero")
            .first()
        )
    if require_accepted_revision and (
        not revision or revision.cotizacion.lead_id != lead.id
        or revision.cotizacion.estado != "aceptada" or not revision.enviada
    ):
        raise ValidationError("No existe una revision comercial enviada y aceptada.")

    effective = effective_quote_values(lead)
    packaging = {
        "sin embalaje": "sin_embalaje",
        "embalaje basico": "basico",
        "embalaje de muebles y artefactos": "muebles",
        "embalaje full": "full",
    }.get(lead.modalidad_servicio, "sin_embalaje")

    servicio = Servicio.objects.create(
        lead_origen=lead,
        cliente=lead.cliente,
        whatsapp_channel=lead.whatsapp_channel,
        asesor=usuario or lead.vendedor_asignado,
        estado=SERVICIO_PENDIENTE,
        fecha_confirmacion=timezone.localdate(),
        es_interprovincial=lead.es_interprovincial,
        tipo_servicio=lead.tipo_servicio,
        distrito_origen=lead.distrito_origen,
        distrito_destino=lead.distrito_destino,
        direccion_origen=lead.direccion_origen,
        direccion_destino=lead.direccion_destino,
        # Lead.piso_* es entero-o-null; Servicio.piso_* es CharField NOT NULL.
        piso_origen="" if lead.piso_origen is None else str(lead.piso_origen),
        piso_destino="" if lead.piso_destino is None else str(lead.piso_destino),
        acceso_origen=lead.acceso_origen,
        acceso_destino=lead.acceso_destino,
        lista_objetos=lead.lista_objetos,
        objetos_pesados=lead.objetos_pesados,
        detalle_carga=effective_load_detail(lead),
        incluye_personal_carga=effective["incluye_personal_carga"],
        cantidad_operarios=lead.cantidad_operarios,
        requiere_desarmado=effective["requiere_desarmado"],
        requiere_armado=effective["requiere_armado"],
        peso_carga_kg=lead.peso_carga_kg,
        volumen_carga_m3=lead.volumen_carga_m3,
        fecha_servicio=lead.fecha_servicio,
        horario_servicio=lead.horario_servicio,
        tipo_embalaje=packaging,
        precio_cotizado=revision.precio_final if revision else lead.precio_cotizado,
        precio_final=revision.precio_final if revision else lead.precio_final,
        precio=revision.precio_final if revision else (lead.precio_final or lead.precio_cotizado),
        dni_ruc=lead.dni_reserva,
        observaciones=lead.observaciones,
    )
    ServicioUbicacion.objects.bulk_create([
        ServicioUbicacion(
            servicio=servicio,
            orden=order,
            tipo=location.tipo,
            distrito=location.distrito,
            direccion=location.direccion,
            piso=location.piso,
            ascensor=location.ascensor,
            acceso_camion=location.acceso_camion,
            distancia_acarreo=location.distancia_acarreo,
            observaciones_acceso=location.observaciones_acceso,
        )
        for order, location in enumerate(route_for_lead(lead))
    ])
    return servicio, True


# ---------------------------------------------------------------------------
# Operaciones sobre una reserva (extraídas de servicios/views.py para que las
# compartan el panel viejo y la API v2). Sin acoplamiento a request/template.
# ---------------------------------------------------------------------------
from decimal import Decimal, InvalidOperation  # noqa: E402

from .models import (  # noqa: E402
    PagoReserva, SERVICIO_CANCELADO, SERVICIO_FINALIZADO,
)

CONCEPTOS_PAGO_REAL = ("adelanto", "parcial", "final")


def registrar_pago(servicio, *, concepto, metodo_pago, monto, usuario=None,
                   fecha_pago=None, observaciones=""):
    try:
        monto = Decimal(str(monto))
    except (InvalidOperation, TypeError):
        raise ValidationError({"amount": "Monto inválido."})
    if monto <= 0:
        raise ValidationError({"amount": "El monto debe ser mayor que cero."})
    if concepto not in dict(PagoReserva._meta.get_field("concepto").choices):
        raise ValidationError({"concept": "Concepto no reconocido."})
    if metodo_pago not in dict(PagoReserva._meta.get_field("metodo_pago").choices):
        raise ValidationError({"method": "Método de pago no reconocido."})
    return PagoReserva.objects.create(
        servicio=servicio, concepto=concepto, metodo_pago=metodo_pago,
        monto=monto, fecha_pago=fecha_pago or timezone.now(),
        observaciones=observaciones or "", usuario_registro=usuario,
    )


def finalizar_servicio(servicio, actor, *, monto_final=None, metodo_final="yape",
                       observaciones=""):
    """Marca la reserva como finalizada. Si se pasa `monto_final`, registra el
    pago final (no puede exceder el saldo; si es menor exige motivo)."""
    with transaction.atomic():
        if monto_final not in (None, ""):
            try:
                monto = Decimal(str(monto_final))
            except (InvalidOperation, TypeError):
                raise ValidationError({"finalAmount": "Monto inválido."})
            saldo = servicio.saldo_pendiente
            if monto > saldo:
                raise ValidationError({"finalAmount": "El monto no puede exceder el saldo pendiente."})
            if monto < saldo and not (observaciones or "").strip():
                raise ValidationError({"note": "Indica el motivo cuando el pago es menor al saldo."})
            registrar_pago(
                servicio, concepto="final", metodo_pago=metodo_final, monto=monto,
                usuario=actor, observaciones=observaciones,
            )
        servicio.estado = SERVICIO_FINALIZADO
        servicio.atendido_por = actor
        servicio.usuario_actualizacion = actor
        servicio.fecha_actualizacion_estado = timezone.now()
        servicio.save(update_fields=[
            "estado", "atendido_por", "usuario_actualizacion", "fecha_actualizacion_estado",
        ])
        return servicio


def cancelar_servicio(servicio, actor, motivo):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError({"reason": "Indica el motivo de la cancelación."})
    servicio.estado = SERVICIO_CANCELADO
    servicio.motivo_cancelacion = motivo
    servicio.atendido_por = actor
    servicio.usuario_actualizacion = actor
    servicio.fecha_actualizacion_estado = timezone.now()
    servicio.save(update_fields=[
        "estado", "motivo_cancelacion", "atendido_por",
        "usuario_actualizacion", "fecha_actualizacion_estado",
    ])
    return servicio


def bookings_queryset(params):
    from apps.api.filters import apply_ordering, apply_search

    qs = Servicio.objects.select_related("cliente", "asesor", "lead_origen").prefetch_related(
        "lead_origen__sesiones_whatsapp")
    qs = apply_search(qs, params.get("search"),
                      ("codigo", "cliente__nombre", "distrito_origen", "distrito_destino"))
    state = (params.get("state") or "").strip()
    _state_es = {
        "pending": "pendiente", "scheduled": "programado", "assigned": "asignado",
        "on_route": "en_ruta", "completed": "finalizado", "cancelled": "cancelado",
    }
    if state in _state_es:
        qs = qs.filter(estado=_state_es[state])
    elif params.get("active") == "1":
        qs = qs.exclude(estado__in=(SERVICIO_FINALIZADO, SERVICIO_CANCELADO))
    qs = apply_ordering(
        qs, params.get("ordering"),
        {"code": "codigo", "serviceDate": "fecha_servicio", "createdAt": "fecha_creacion"},
        ("-fecha_creacion", "-id"),
    )
    return qs
