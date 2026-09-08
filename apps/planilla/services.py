"""Consultas y helpers del módulo Planilla."""
import calendar
from datetime import date as _date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum

from apps.api.filters import apply_active_filter, apply_ordering
from apps.planilla.models import (
    ConfiguracionPlanilla, MovimientoCompensacion, Pago, RegistroAsistencia, SaldoHorasMes,
)

_ZERO = Decimal("0")
_Q2 = Decimal("0.01")


def _money(x):
    return Decimal(x).quantize(_Q2, rounding=ROUND_HALF_UP)


def _ultimo_dia(anio, mes):
    return _date(anio, mes, calendar.monthrange(anio, mes)[1])

_CONFIG_ORDER = {
    "hiredOn": "fecha_ingreso",
    "contractType": "tipo_contrato",
    "createdAt": "creado_en",
}


def configs_queryset(params):
    qs = ConfiguracionPlanilla.objects.select_related("conductor", "ayudante", "usuario")

    tipo = (params.get("workerType") or params.get("type") or "").strip()
    if tipo:
        qs = qs.filter(tipo=tipo)

    worker_id = params.get("workerId")
    if worker_id:
        qs = qs.filter(
            Q(tipo="conductor", conductor_id=worker_id)
            | Q(tipo="ayudante", ayudante_id=worker_id)
            | Q(tipo="asesor", usuario_id=worker_id)
        )

    contrato = (params.get("contractType") or "").strip()
    if contrato:
        qs = qs.filter(tipo_contrato=contrato)

    qs = apply_active_filter(qs, params.get("status"))

    term = (params.get("search") or "").strip()
    if term:
        qs = qs.filter(
            Q(conductor__nombre__icontains=term)
            | Q(ayudante__nombre__icontains=term)
            | Q(usuario__first_name__icontains=term)
            | Q(usuario__last_name__icontains=term)
            | Q(usuario__username__icontains=term)
            | Q(conductor__dni__icontains=term)
            | Q(ayudante__dni__icontains=term)
        )

    return apply_ordering(qs, params.get("ordering"), _CONFIG_ORDER, ("fecha_ingreso", "id"))


# ── Asistencia ─────────────────────────────────────────────────────────

def attendance_queryset(params):
    qs = RegistroAsistencia.objects.select_related(
        "trabajador", "trabajador__conductor", "trabajador__ayudante", "trabajador__usuario",
    )
    tid = params.get("trabajadorId")
    if tid:
        qs = qs.filter(trabajador_id=tid)
    if params.get("date"):
        qs = qs.filter(fecha=params["date"])
    if params.get("from"):
        qs = qs.filter(fecha__gte=params["from"])
    if params.get("to"):
        qs = qs.filter(fecha__lte=params["to"])
    tipo = (params.get("dayType") or "").strip()
    if tipo:
        qs = qs.filter(tipo_dia=tipo)
    return apply_ordering(qs, params.get("ordering"), {"date": "fecha"}, ("-fecha", "id"))


def month_delta(trabajador, fecha):
    """Σ de Δ de los días trabajados del 1° del mes de `fecha` hasta `fecha`."""
    inicio = fecha.replace(day=1)
    total = (RegistroAsistencia.objects
             .filter(trabajador=trabajador, fecha__gte=inicio, fecha__lte=fecha,
                     tipo_dia=RegistroAsistencia.TIPO_TRABAJADO)
             .aggregate(s=Sum("delta_dia"))["s"])
    return total or _ZERO


def dia_planilla(fecha):
    """Reporte de la asistencia YA registrada en `fecha`: una fila por cada
    RegistroAsistencia de ese día, con las horas del día y el saldo de horas
    acumulado (desde el ingreso, no solo del mes)."""
    regs = (RegistroAsistencia.objects
            .filter(fecha=fecha)
            .select_related("trabajador", "trabajador__conductor",
                            "trabajador__ayudante", "trabajador__usuario"))
    filas = []
    for r in regs:
        c = r.trabajador
        filas.append({
            "trabajadorId": c.id,
            "workerType": c.tipo,
            "workerName": c.nombre,
            "contractType": c.tipo_contrato,
            "workdayHours": c.horas_jornada,
            "lunchHours": c.horas_refrigerio,
            "attendanceId": r.id,
            "dayType": r.tipo_dia,
            "clockIn": r.hora_ingreso.strftime("%H:%M") if r.hora_ingreso else None,
            "clockOut": r.hora_salida.strftime("%H:%M") if r.hora_salida else None,
            "workedHours": float(r.horas_trabajadas),
            "delta": float(r.delta_dia),
            "note": r.observacion,
            "balanceHours": float(saldo_horas(c, fecha)),
        })
    filas.sort(key=lambda x: x["workerName"].lower())
    return filas


def upsert_asistencia(*, trabajador, fecha, tipo_dia, hora_ingreso=None, hora_salida=None,
                      observacion="", usuario=None):
    reg, _created = RegistroAsistencia.objects.get_or_create(
        trabajador=trabajador, fecha=fecha,
        defaults={
            "horas_jornada_dia": trabajador.horas_jornada,
            "horas_refrigerio_dia": trabajador.horas_refrigerio,
        },
    )
    reg.tipo_dia = tipo_dia
    reg.hora_ingreso = hora_ingreso
    reg.hora_salida = hora_salida
    reg.observacion = observacion or ""
    if usuario is not None:
        reg.registrado_por = usuario
    reg.save()
    return reg


# ── Saldo de horas ────────────────────────────────────────────────────

def _deltas(trabajador, d1, d2):
    total = (RegistroAsistencia.objects
             .filter(trabajador=trabajador, tipo_dia=RegistroAsistencia.TIPO_TRABAJADO,
                     fecha__gte=d1, fecha__lte=d2)
             .aggregate(s=Sum("delta_dia"))["s"])
    return total or _ZERO


def _comps(trabajador, d1, d2):
    total = (MovimientoCompensacion.objects
             .filter(trabajador=trabajador, fecha__gte=d1, fecha__lte=d2)
             .aggregate(s=Sum("horas"))["s"])
    return total or _ZERO


def _aperturas_hasta(trabajador, fecha):
    """{(anio, mes): apertura} para cada mes desde el ingreso hasta el mes de
    `fecha`, iterando hacia adelante (cierre de un mes = apertura del siguiente,
    salvo override manual en SaldoHorasMes)."""
    ing = trabajador.fecha_ingreso
    overrides = {
        (r.anio, r.mes): r.saldo_apertura
        for r in SaldoHorasMes.objects.filter(trabajador=trabajador, editado_manual=True)
    }
    aperturas = {}
    apertura = _ZERO
    y, m = ing.year, ing.month
    ty, tm = fecha.year, fecha.month
    while (y, m) <= (ty, tm):
        if (y, m) in overrides:
            apertura = overrides[(y, m)]
        aperturas[(y, m)] = apertura
        d1 = _date(y, m, 1)
        d2 = _ultimo_dia(y, m)
        apertura = apertura + _deltas(trabajador, d1, d2) + _comps(trabajador, d1, d2)
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return aperturas


def saldo_horas(trabajador, fecha):
    """Saldo de horas (con signo; + = la empresa le debe) a `fecha`."""
    apertura = _aperturas_hasta(trabajador, fecha).get((fecha.year, fecha.month), _ZERO)
    d1 = fecha.replace(day=1)
    return apertura + _deltas(trabajador, d1, fecha) + _comps(trabajador, d1, fecha)


# ── Compensaciones ────────────────────────────────────────────────────

def compensations_queryset(params):
    qs = MovimientoCompensacion.objects.select_related(
        "trabajador", "trabajador__conductor", "trabajador__ayudante", "trabajador__usuario",
        "asistencia",
    )
    tid = params.get("trabajadorId")
    if tid:
        qs = qs.filter(trabajador_id=tid)
    if params.get("from"):
        qs = qs.filter(fecha__gte=params["from"])
    if params.get("to"):
        qs = qs.filter(fecha__lte=params["to"])
    tipo = (params.get("kind") or "").strip()
    if tipo:
        qs = qs.filter(tipo=tipo)
    return apply_ordering(qs, params.get("ordering"), {"date": "fecha"}, ("-fecha", "-id"))


def faltas_pendientes(desde=None, hasta=None):
    """Faltas sin compensación registrada. Por cada una: el saldo de horas del
    trabajador a esa fecha y si alcanza para compensar (saldo >= jornada del día)."""
    qs = (RegistroAsistencia.objects
          .filter(tipo_dia=RegistroAsistencia.TIPO_FALTA)
          .select_related("trabajador", "trabajador__conductor",
                          "trabajador__ayudante", "trabajador__usuario")
          .order_by("fecha", "id"))
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)
    compensadas = set(
        MovimientoCompensacion.objects
        .filter(tipo=MovimientoCompensacion.TIPO_FALTA_COMPENSADA, asistencia__in=qs)
        .values_list("asistencia_id", flat=True)
    )
    filas = []
    for r in qs:
        if r.id in compensadas:
            continue
        saldo = saldo_horas(r.trabajador, r.fecha)
        jornada = r.horas_jornada_dia or r.trabajador.horas_jornada
        filas.append({
            "attendanceId": r.id,
            "trabajadorId": r.trabajador_id,
            "workerName": r.trabajador.nombre,
            "date": r.fecha.isoformat(),
            "workdayHours": float(jornada),
            "balanceAtDate": float(saldo),
            "compensable": saldo >= jornada,
        })
    return filas


# ── Pagos ─────────────────────────────────────────────────────────────

def payments_queryset(params):
    qs = Pago.objects.select_related(
        "trabajador", "trabajador__conductor", "trabajador__ayudante", "trabajador__usuario",
    )
    if params.get("trabajadorId"):
        qs = qs.filter(trabajador_id=params["trabajadorId"])
    if params.get("from"):
        qs = qs.filter(periodo_hasta__gte=params["from"])
    if params.get("to"):
        qs = qs.filter(periodo_hasta__lte=params["to"])
    paid = params.get("paid")
    if paid in ("true", "1"):
        qs = qs.filter(pagado=True)
    elif paid in ("false", "0"):
        qs = qs.filter(pagado=False)
    return apply_ordering(qs, params.get("ordering"), {"periodTo": "periodo_hasta"},
                          ("-periodo_hasta", "-id"))


def calcular_pago(trabajador, desde, hasta, tipo):
    """Preview del pago (sin guardar). Reglas confirmadas con el usuario."""
    regs = list(RegistroAsistencia.objects.filter(
        trabajador=trabajador, fecha__gte=desde, fecha__lte=hasta,
    ))
    dias_trab = sum(1 for r in regs
                    if r.tipo_dia == RegistroAsistencia.TIPO_TRABAJADO and r.hora_ingreso)
    faltas = [r for r in regs if r.tipo_dia in (
        RegistroAsistencia.TIPO_FALTA, RegistroAsistencia.TIPO_LICENCIA_SG,
    )]
    comp_ids = set(MovimientoCompensacion.objects.filter(
        trabajador=trabajador, tipo=MovimientoCompensacion.TIPO_FALTA_COMPENSADA,
        asistencia_id__in=[r.id for r in faltas],
    ).values_list("asistencia_id", flat=True))
    faltas_nc = [r for r in faltas if r.id not in comp_ids]

    if trabajador.tipo_contrato == ConfiguracionPlanilla.CONTRATO_HONORARIOS:
        bruto = _money(Decimal(str(trabajador.monto_dia or 0)) * dias_trab)
        afp = _ZERO
    else:
        mes = Decimal(str(trabajador.monto_mes or 0))
        valor_dia = mes / Decimal("30")
        if tipo == Pago.TIPO_FIN_DE_MES:
            base = mes - valor_dia * len(faltas_nc)
        elif tipo == Pago.TIPO_QUINCENA:
            base = mes / Decimal("2") - valor_dia * len(faltas_nc)
        elif tipo == Pago.TIPO_POR_DIAS:
            # proporcional: días calendario del vínculo dentro del rango − faltas
            inicio = max(desde, trabajador.fecha_ingreso)
            dias_cal = (hasta - inicio).days + 1 if inicio <= hasta else 0
            dias_pagables = max(0, dias_cal - len(faltas_nc))
            base = valor_dia * dias_pagables
        else:  # adelanto: monto libre
            base = _ZERO
        bruto = _money(base)
        afp = _money(bruto * Decimal(str(trabajador.pct_afp or 0)) / Decimal("100"))

    neto = _money(bruto - afp)
    dias_pagables = None
    if (trabajador.tipo_contrato == ConfiguracionPlanilla.CONTRATO_PLANILLA
            and tipo == Pago.TIPO_POR_DIAS):
        _ini = max(desde, trabajador.fecha_ingreso)
        _cal = (hasta - _ini).days + 1 if _ini <= hasta else 0
        dias_pagables = max(0, _cal - len(faltas_nc))
    return {
        "daysWorked": dias_trab,
        "payableDays": dias_pagables,
        "absencesDeducted": len(faltas_nc),
        "grossAmount": float(bruto),
        "afpDeduction": float(afp),
        "netAmount": float(neto),
        "valorDia": float((trabajador.valor_dia).quantize(Decimal("0.0001"))),
        "valorHora": float((trabajador.valor_hora).quantize(Decimal("0.0001"))),
        "detalle": {
            "contrato": trabajador.tipo_contrato,
            "tipo": tipo,
            "faltasCompensadas": len(faltas) - len(faltas_nc),
        },
    }


# ── Vacaciones y resumen ──────────────────────────────────────────────

def vacaciones_info(trabajador, fecha):
    """15 días por año cumplido; truncas del año en curso para liquidación."""
    if trabajador.tipo_contrato == ConfiguracionPlanilla.CONTRATO_HONORARIOS:
        return {"aplica": False}

    ing = trabajador.fecha_ingreso
    anios = fecha.year - ing.year - (
        1 if (fecha.month, fecha.day) < (ing.month, ing.day) else 0
    )
    anios = max(0, anios)
    aniv_mes = ing.month
    aniv_anio = ing.year + anios
    meses = (fecha.year - aniv_anio) * 12 + (fecha.month - aniv_mes)
    if fecha.day < min(ing.day, 28):
        meses -= 1
    meses = max(0, min(12, meses))

    gozados = RegistroAsistencia.objects.filter(
        trabajador=trabajador, tipo_dia=RegistroAsistencia.TIPO_VACACIONES,
    ).count()
    ganadas = anios * 15
    pendientes = ganadas - gozados
    truncas = (Decimal(15) * Decimal(meses) / Decimal(12)).quantize(_Q2)
    vd = trabajador.valor_dia
    liquidacion = _money(vd * (Decimal(max(0, pendientes)) + truncas))
    return {
        "aplica": True,
        "yearsCompleted": anios,
        "daysEarned": ganadas,
        "daysTaken": gozados,
        "daysPending": pendientes,
        "daysAccruedCurrentYear": float(truncas),
        "valorDia": float(vd.quantize(_Q2)),
        "liquidationAmount": float(liquidacion),
    }


def _resumen_fila(c, fecha):
    d1 = fecha.replace(day=1)
    faltas_qs = RegistroAsistencia.objects.filter(
        trabajador=c, fecha__gte=d1, fecha__lte=fecha, tipo_dia=RegistroAsistencia.TIPO_FALTA,
    )
    n_faltas = faltas_qs.count()
    comp_ids = MovimientoCompensacion.objects.filter(
        trabajador=c, tipo=MovimientoCompensacion.TIPO_FALTA_COMPENSADA,
        asistencia__in=faltas_qs,
    ).values_list("asistencia_id", flat=True)
    faltas_nc = n_faltas - len(set(comp_ids))
    dias_trab = RegistroAsistencia.objects.filter(
        trabajador=c, fecha__gte=d1, fecha__lte=fecha,
        tipo_dia=RegistroAsistencia.TIPO_TRABAJADO, hora_ingreso__isnull=False,
    ).count()
    saldo = saldo_horas(c, fecha)
    vac = vacaciones_info(c, fecha)
    ultimo = Pago.objects.filter(trabajador=c).order_by("-periodo_hasta", "-id").first()
    desde = (ultimo.periodo_hasta + timedelta(days=1)) if ultimo else d1
    if desde > fecha:
        desde = d1
    est = calcular_pago(c, desde, fecha, "fin_de_mes")
    return {
        "trabajadorId": c.id,
        "workerType": c.tipo,
        "workerName": c.nombre,
        "contractType": c.tipo_contrato,
        "balanceHours": float(saldo),
        "balanceValue": float(_money(saldo * c.valor_hora)),
        "absencesMonth": n_faltas,
        "absencesUnresolved": faltas_nc,
        "daysWorkedMonth": dias_trab,
        "vacationDaysPending": vac["daysPending"] if vac.get("aplica") else None,
        "estimatedFrom": desde.isoformat(),
        "estimatedNet": est["netAmount"],
        "lastPayment": None if not ultimo else {
            "periodTo": ultimo.periodo_hasta.isoformat(),
            "netAmount": float(ultimo.monto_neto),
            "paid": ultimo.pagado,
        },
    }


def payroll_summary(fecha):
    configs = (ConfiguracionPlanilla.objects
               .filter(activo=True)
               .select_related("conductor", "ayudante", "usuario"))
    filas = [_resumen_fila(c, fecha) for c in configs]
    filas.sort(key=lambda r: r["workerName"].lower())
    return filas


def worker_payroll(trabajador, fecha):
    d1 = fecha.replace(day=1)
    regs = list(RegistroAsistencia.objects
                .filter(trabajador=trabajador, fecha__lte=fecha)
                .order_by("-fecha")[:31])
    comps = list(MovimientoCompensacion.objects
                 .filter(trabajador=trabajador).order_by("-fecha", "-id")[:20])
    pagos = list(Pago.objects.filter(trabajador=trabajador).order_by("-periodo_hasta", "-id")[:12])
    return {
        "worker": {
            "id": trabajador.id, "name": trabajador.nombre, "type": trabajador.tipo,
            "contractType": trabajador.tipo_contrato,
            "workdayHours": float(trabajador.horas_jornada),
            "hiredOn": trabajador.fecha_ingreso.isoformat(),
            "amountPerMonth": float(trabajador.monto_mes) if trabajador.monto_mes is not None else None,
            "amountPerDay": float(trabajador.monto_dia) if trabajador.monto_dia is not None else None,
            "valorDia": float(trabajador.valor_dia.quantize(_Q2)),
            "valorHora": float(trabajador.valor_hora.quantize(Decimal("0.0001"))),
        },
        "balanceHours": float(saldo_horas(trabajador, fecha)),
        "monthDelta": float(_deltas(trabajador, d1, fecha)),
        "vacations": vacaciones_info(trabajador, fecha),
        "recentAttendance": [
            {
                "date": r.fecha.isoformat(), "dayType": r.tipo_dia,
                "clockIn": r.hora_ingreso.strftime("%H:%M") if r.hora_ingreso else None,
                "clockOut": r.hora_salida.strftime("%H:%M") if r.hora_salida else None,
                "delta": float(r.delta_dia),
            }
            for r in regs
        ],
        "compensations": [
            {
                "date": m.fecha.isoformat(), "kind": m.tipo, "hours": float(m.horas),
                "reason": m.motivo,
            }
            for m in comps
        ],
        "payments": [
            {
                "periodFrom": p.periodo_desde.isoformat(), "periodTo": p.periodo_hasta.isoformat(),
                "type": p.tipo, "netAmount": float(p.monto_neto), "paid": p.pagado,
                "paidOn": p.fecha_pago.isoformat() if p.fecha_pago else None,
            }
            for p in pagos
        ],
    }
