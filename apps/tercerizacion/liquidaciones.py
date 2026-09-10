"""P1 · Liquidaciones de tercerización.

Cuando se adjudica una carga a un transportista se genera una `Liquidacion`: qué
cobra la plataforma al cliente, qué se le paga al transportista, y la comisión.
Finanzas concilia y marca liquidado; el transportista lo ve en "Mis cobros".

La **comisión** se resuelve por esta precedencia (`comision_para`):
  1. servicio marcado `sin_comision` a mano           → 0
  2. precio < `monto_minimo_comisionable` (config)     → 0
  3. cliente con suscripción activa                    → regla del plan  (hook, hoy inerte)
  4. el spread real venta − costo                      → comisión
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.tercerizacion.models import Liquidacion

_Q = Decimal("0.01")


def _dec(v):
    if v is None or v == "":
        return Decimal(0)
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _suscripcion_cubre_comision(servicio):
    """Hook de la modalidad Suscripción (P5). Devuelve un dict con la regla del
    plan del cliente, o None si no aplica / no está construido todavía."""
    cliente = getattr(servicio, "cliente", None)
    getter = getattr(cliente, "suscripcion_activa", None) if cliente else None
    if callable(getter):
        plan = getter()
        if plan is not None:
            return {"pct": _dec(getattr(plan, "comision_pct", 0)), "fuente": "suscripcion"}
    return None


def comision_para(servicio, *, precio=None, costo=None):
    """{'pct', 'monto', 'sin_comision', 'motivo'} para un servicio tercerizado.

    `precio` = venta al cliente (default `servicio.precio`).
    `costo`  = pactado con el transportista (obligatorio pasarlo, o queda 0).
    """
    from apps.servicios.models import ConfiguracionOperaciones

    precio = _dec(precio if precio is not None else servicio.precio)
    costo = _dec(costo)
    spread = max(precio - costo, Decimal(0))

    if getattr(servicio, "sin_comision", False):
        return {"pct": Decimal(0), "monto": Decimal(0), "sin_comision": True,
                "motivo": servicio.sin_comision_motivo or "Exonerado manualmente"}

    minimo = _dec(ConfiguracionOperaciones.get_solo().monto_minimo_comisionable)
    if minimo > 0 and precio < minimo:
        return {"pct": Decimal(0), "monto": Decimal(0), "sin_comision": True,
                "motivo": f"Servicio por debajo del mínimo comisionable (S/ {minimo:g})"}

    sus = _suscripcion_cubre_comision(servicio)
    if sus is not None:
        pct = sus["pct"]
        monto = (precio * pct / Decimal(100)).quantize(_Q, ROUND_HALF_UP)
        return {"pct": pct, "monto": monto, "sin_comision": monto == 0,
                "motivo": "Cliente con suscripción activa"}

    pct = (spread / precio * Decimal(100)).quantize(_Q, ROUND_HALF_UP) if precio else Decimal(0)
    return {"pct": pct, "monto": spread.quantize(_Q, ROUND_HALF_UP),
            "sin_comision": spread == 0, "motivo": ""}


def _calc_neto(medio, precio, costo, comision_monto):
    """El neto entre plataforma y transportista según cómo cobró el cliente."""
    if medio == Liquidacion.MEDIO_EFECTIVO_TRANSPORTISTA:
        # el transportista cobró el precio completo en mano → nos debe la comisión
        return (-comision_monto).quantize(_Q)
    # el cliente pagó a la plataforma (o está por definir) → le pagamos su parte
    return (precio - comision_monto).quantize(_Q)


@transaction.atomic
def generar_liquidacion(programacion, *, usuario=None):
    """Crea (o refresca, si sigue pendiente) la liquidación de una programación
    tercerizada. Idempotente. Devuelve la `Liquidacion` o None si no aplica."""
    if not programacion.transportista_id:
        return None

    servicio = programacion.servicio
    precio = _dec(servicio.precio)
    costo = _dec(programacion.monto)
    com = comision_para(servicio, precio=precio, costo=costo)

    liq, creada = Liquidacion.objects.select_for_update().get_or_create(
        programacion=programacion,
        defaults={
            "servicio": servicio,
            "transportista_id": programacion.transportista_id,
        },
    )
    if not creada and liq.estado not in (Liquidacion.ESTADO_PENDIENTE, Liquidacion.ESTADO_CONCILIADA):
        return liq  # ya liquidada / anulada: no se toca

    liq.servicio = servicio
    liq.transportista_id = programacion.transportista_id
    liq.precio_servicio = precio
    liq.costo_transportista = costo
    liq.comision_pct = com["pct"]
    liq.comision_monto = com["monto"]
    liq.sin_comision = com["sin_comision"]
    liq.exencion_motivo = com["motivo"]
    liq.neto = _calc_neto(liq.medio_cobro_cliente, precio, costo, com["monto"])
    liq.save()
    return liq


@transaction.atomic
def recalcular(liq):
    """Vuelve a calcular importes desde la programación/servicio actuales.
    Solo si sigue pendiente o conciliada."""
    if liq.estado in (Liquidacion.ESTADO_PAGADA, Liquidacion.ESTADO_ANULADA):
        return liq
    return generar_liquidacion(liq.programacion)


@transaction.atomic
def set_medio_cobro(liq, medio, *, usuario=None):
    if medio not in dict(Liquidacion.MEDIOS):
        from django.core.exceptions import ValidationError
        raise ValidationError({"collectionMethod": "Medio de cobro no válido."})
    liq.medio_cobro_cliente = medio
    liq.neto = _calc_neto(medio, liq.precio_servicio, liq.costo_transportista, liq.comision_monto)
    if liq.estado == Liquidacion.ESTADO_PENDIENTE and medio != Liquidacion.MEDIO_POR_DEFINIR:
        liq.estado = Liquidacion.ESTADO_CONCILIADA
    liq.save(update_fields=["medio_cobro_cliente", "neto", "estado", "actualizado_en"])
    return liq


@transaction.atomic
def marcar_liquidada(liq, *, usuario=None, referencia="", fecha=None, comprobante="", nota=""):
    from django.core.exceptions import ValidationError
    if liq.estado == Liquidacion.ESTADO_ANULADA:
        raise ValidationError("La liquidación está anulada.")
    if liq.medio_cobro_cliente == Liquidacion.MEDIO_POR_DEFINIR:
        raise ValidationError("Definí primero cómo cobró el cliente.")
    liq.estado = Liquidacion.ESTADO_PAGADA
    liq.fecha_liquidacion = fecha or timezone.localdate()
    liq.referencia_pago = referencia or ""
    liq.comprobante = comprobante or ""
    if nota:
        liq.nota = (liq.nota + "\n" + nota).strip() if liq.nota else nota
    liq.liquidado_por = usuario
    liq.save()
    return liq


@transaction.atomic
def anular_liquidacion(liq, *, usuario=None, motivo=""):
    liq.estado = Liquidacion.ESTADO_ANULADA
    if motivo:
        liq.nota = (liq.nota + f"\nAnulada: {motivo}").strip()
    liq.liquidado_por = usuario
    liq.save(update_fields=["estado", "nota", "liquidado_por", "actualizado_en"])
    return liq


def resumen_transportista(transportista):
    """Totales de 'Mis cobros' para el Portal del Transportista."""
    qs = Liquidacion.objects.filter(transportista=transportista).exclude(
        estado=Liquidacion.ESTADO_ANULADA,
    )
    por_cobrar = pagado = te_debemos = le_debes = Decimal(0)
    for liq in qs:
        if liq.estado == Liquidacion.ESTADO_PAGADA:
            pagado += liq.neto
        elif liq.neto > 0:
            por_cobrar += liq.neto
            te_debemos += liq.neto
        elif liq.neto < 0:
            le_debes += -liq.neto
    return {
        "pendingPayout": float(por_cobrar),
        "settled": float(pagado),
        "youOwePlatform": float(le_debes),
    }
