"""P2 · Plan de cobro de un servicio (cuotas).

Cada reserva tiene un plan de cuotas: cuándo se espera cobrar cada parte
(`disparador`) y cuánto (`base` + `valor`). Un `PagoReserva` que entra salda la
cuota más antigua pendiente (o una específica). El total siempre sigue a
`servicio.precio` mientras las cuotas no estén pagadas.
"""
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import CuotaServicio

_Q = Decimal("0.01")
D = CuotaServicio


def _dec(v):
    if v in (None, ""):
        return Decimal(0)
    return v if isinstance(v, Decimal) else Decimal(str(v))


# preset -> lista de (disparador, base, valor, dias)
PRESETS = {
    "total_reserva": ("Todo al reservar", [(D.DISP_RESERVA, "porcentaje", 100, None)]),
    "adelanto_saldo": ("Adelanto + saldo en destino", None),  # usa adelanto_pct_default
    "mitad_origen_destino": ("50 % origen / 50 % destino", [
        (D.DISP_ORIGEN, "porcentaje", 50, None), (D.DISP_DESTINO, "porcentaje", 50, None),
    ]),
    "total_destino": ("Todo en el destino", [(D.DISP_DESTINO, "porcentaje", 100, None)]),
    "credito_15": ("Crédito 15 días", [(D.DISP_DIAS, "porcentaje", 100, 15)]),
    "credito_30": ("Crédito 30 días", [(D.DISP_DIAS, "porcentaje", 100, 30)]),
}


def presets_disponibles():
    return [{"key": k, "label": lbl} for k, (lbl, _) in PRESETS.items()]


def _specs_para(preset, *, adelanto_pct):
    if preset == "adelanto_saldo":
        ade = _dec(adelanto_pct)
        return [
            (D.DISP_RESERVA, "porcentaje", ade, None),
            (D.DISP_DESTINO, "porcentaje", Decimal(100) - ade, None),
        ]
    if preset not in PRESETS:
        raise ValidationError({"scheme": "Esquema de cobro no reconocido."})
    return PRESETS[preset][1]


def _fecha_venc(spec_disp, dias, servicio):
    if spec_disp == D.DISP_DIAS and servicio.fecha_servicio and dias:
        return servicio.fecha_servicio + timedelta(days=int(dias))
    return None


def _monto_de(base, valor, total):
    if base == D.BASE_MONTO:
        return _dec(valor).quantize(_Q)
    return (total * _dec(valor) / Decimal(100)).quantize(_Q, ROUND_HALF_UP)


@transaction.atomic
def aplicar_esquema(servicio, preset=None, *, cuotas=None, usuario=None):
    """Reemplaza el plan de cobro. `preset` = clave de PRESETS, o `cuotas` = lista
    de dicts {trigger, base, value, days?, dueDate?}. Conserva los pagos ya
    hechos re-vinculándolos a la primera cuota. Devuelve la lista de CuotaServicio.
    """
    from apps.servicios.models import ConfiguracionOperaciones

    total = _dec(servicio.precio)
    if cuotas is not None:
        specs = []
        for c in cuotas:
            disp = c.get("trigger")
            if disp not in dict(D.DISPARADORES):
                raise ValidationError({"installments": f"Disparador no válido: {disp}"})
            base = c.get("base", "porcentaje")
            specs.append((disp, base, _dec(c.get("value")), c.get("days")))
    else:
        cfg = ConfiguracionOperaciones.get_solo()
        specs = _specs_para(preset or cfg.esquema_cobro_default, adelanto_pct=cfg.adelanto_pct_default)

    # valida que los porcentajes cierren en 100 (si todo es porcentaje)
    if all(b == "porcentaje" for _, b, _, _ in specs):
        suma = sum((_dec(v) for _, _, v, _ in specs), Decimal(0))
        if suma != Decimal(100):
            raise ValidationError({"installments": f"Los porcentajes deben sumar 100 (suman {suma:g})."})

    pagos_previos = list(servicio.pagos.all())
    servicio.cuotas.all().delete()

    creadas = []
    for i, (disp, base, valor, dias) in enumerate(specs, start=1):
        creadas.append(CuotaServicio.objects.create(
            servicio=servicio, orden=i, disparador=disp, base=base, valor=valor,
            dias=dias if disp == D.DISP_DIAS else None,
            fecha_vencimiento=_fecha_venc(disp, dias, servicio),
            monto=_monto_de(base, valor, total),
        ))
    if pagos_previos and creadas:
        for p in pagos_previos:
            p.cuota = creadas[0]
        type(pagos_previos[0]).objects.bulk_update(pagos_previos, ["cuota"])
    return creadas


@transaction.atomic
def recalcular_cuotas(servicio):
    """Refresca el monto de las cuotas cuando cambia `servicio.precio`. Respeta
    las cuotas ya pagadas (no las baja de lo cobrado)."""
    total = _dec(servicio.precio)
    for c in servicio.cuotas.all():
        nuevo = _monto_de(c.base, c.valor, total)
        pagado = c.pagado
        c.monto = max(nuevo, pagado)
        c.save(update_fields=["monto", "actualizado_en"])


@transaction.atomic
def asignar_pago(pago, *, cuota_id=None):
    """Vincula un `PagoReserva` a una cuota: la indicada, o la más antigua sin
    saldar. Si sobra, el resto queda sin asignar (se verá como excedente)."""
    servicio = pago.servicio
    if cuota_id:
        pago.cuota = servicio.cuotas.filter(pk=cuota_id).first()
        pago.save(update_fields=["cuota"])
        return pago
    for c in servicio.cuotas.order_by("orden"):
        if c.pagado < c.monto:
            pago.cuota = c
            pago.save(update_fields=["cuota"])
            return pago
    return pago


def estado_cobro(servicio):
    """{total, paid, balance, scheme, installments:[...]} para la UI."""
    total = _dec(servicio.precio)
    cuotas = list(servicio.cuotas.order_by("orden"))
    pagado = servicio.total_pagado
    return {
        "total": float(total),
        "paid": float(pagado),
        "balance": float(max(total - pagado, Decimal(0))),
        "hasPlan": bool(cuotas),
        "installments": [
            {
                "id": c.id,
                "order": c.orden,
                "trigger": c.disparador,
                "triggerLabel": c.get_disparador_display(),
                "days": c.dias,
                "dueDate": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else None,
                "base": c.base,
                "value": float(c.valor),
                "amount": float(c.monto),
                "paid": float(c.pagado),
                "state": c.estado,
            }
            for c in cuotas
        ],
    }
