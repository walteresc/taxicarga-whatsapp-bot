"""Órdenes de pago: crear, procesar el cargo, confirmar (→ PagoReserva)."""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.pagos.models import OrdenPago
from apps.pagos.pasarelas import build_pasarela

_VIGENCIA_DIAS = 7


def _dec(v):
    return v if isinstance(v, Decimal) else Decimal(str(v or 0))


def _cuota_pendiente(servicio, cuota_id=None):
    cuotas = servicio.cuotas.order_by("orden")
    if cuota_id:
        c = cuotas.filter(pk=cuota_id).first()
        if not c:
            raise ValidationError({"installmentId": "Cuota no encontrada."})
        return c
    for c in cuotas:
        if c.pagado < c.monto:
            return c
    return None


@transaction.atomic
def crear_orden(servicio, *, cuota_id=None, monto=None, concepto=None, usuario=None,
                origen="link", email=""):
    """Crea (o reutiliza si hay una viva para la misma cuota) una orden de pago."""
    cuota = _cuota_pendiente(servicio, cuota_id)
    if monto in (None, ""):
        if cuota is None:
            raise ValidationError("El servicio no tiene saldo pendiente.")
        monto = cuota.monto - cuota.pagado
    monto = _dec(monto)
    if monto <= 0:
        raise ValidationError({"amount": "El monto debe ser mayor que cero."})

    if cuota is not None:
        viva = cuota.ordenes_pago.filter(
            estado__in=[OrdenPago.ESTADO_CREADA, OrdenPago.ESTADO_PROCESANDO],
        ).first()
        if viva and viva.pagable and viva.monto == monto:
            return viva

    if not concepto:
        primera = not servicio.pagos.filter(concepto__in=("adelanto", "parcial", "final")).exists()
        concepto = "adelanto" if primera else "parcial"

    pasarela = build_pasarela()
    return OrdenPago.objects.create(
        servicio=servicio, cuota=cuota, concepto=concepto, monto=monto,
        email_pagador=email or (servicio.cliente.correo if servicio.cliente_id else ""),
        pasarela=pasarela.nombre, creado_por=usuario, origen=origen,
        expira_en=timezone.now() + timedelta(days=_VIGENCIA_DIAS),
    )


@transaction.atomic
def procesar_cargo(orden, *, source_token, email=""):
    """Ejecuta el cargo síncrono (tarjeta / Yape). Devuelve la orden actualizada."""
    orden = OrdenPago.objects.select_for_update().get(pk=orden.pk)
    if orden.estado == OrdenPago.ESTADO_PAGADA:
        return orden
    if not orden.pagable:
        raise ValidationError("La orden de pago venció o ya no es válida.")

    orden.intentos += 1
    orden.estado = OrdenPago.ESTADO_PROCESANDO
    orden.save(update_fields=["intentos", "estado", "actualizado_en"])

    res = build_pasarela(orden.pasarela).crear_cargo(orden, source_token=source_token, email=email)
    orden.respuesta = res.raw or {}
    if res.ok and res.estado == "pagada":
        return _confirmar(orden, external_id=res.external_id)
    orden.estado = OrdenPago.ESTADO_FALLIDA
    orden.detalle_error = (res.mensaje or "Cargo rechazado.")[:300]
    orden.save(update_fields=["estado", "detalle_error", "respuesta", "actualizado_en"])
    return orden


@transaction.atomic
def confirmar_por_webhook(pasarela_nombre, external_id, estado):
    orden = (
        OrdenPago.objects.select_for_update()
        .filter(pasarela=pasarela_nombre, external_id=external_id)
        .exclude(estado=OrdenPago.ESTADO_PAGADA)
        .first()
    )
    if not orden:
        return None
    if estado == "pagada":
        return _confirmar(orden, external_id=external_id)
    orden.estado = OrdenPago.ESTADO_FALLIDA
    orden.save(update_fields=["estado", "actualizado_en"])
    return orden


def _confirmar(orden, *, external_id):
    """Marca la orden pagada y genera el PagoReserva (que salda la cuota).
    Idempotente."""
    from apps.servicios.services import registrar_pago

    if orden.estado == OrdenPago.ESTADO_PAGADA:
        return orden
    orden.external_id = external_id or orden.external_id
    orden.estado = OrdenPago.ESTADO_PAGADA
    orden.pagado_en = timezone.now()

    if not orden.pago_generado_id:
        pago = registrar_pago(
            orden.servicio, concepto=orden.concepto, metodo_pago="tarjeta",
            monto=orden.monto, usuario=orden.creado_por,
            cuota_id=orden.cuota_id,
            observaciones=f"Pago online · {orden.pasarela} · {orden.external_id}",
        )
        orden.pago_generado = pago
    orden.save(update_fields=["external_id", "estado", "pagado_en", "pago_generado", "respuesta", "actualizado_en"])
    return orden


def expirar_vencidas():
    n = OrdenPago.objects.filter(
        estado__in=[OrdenPago.ESTADO_CREADA, OrdenPago.ESTADO_PROCESANDO],
        expira_en__lt=timezone.now(),
    ).update(estado=OrdenPago.ESTADO_EXPIRADA)
    return n
