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
    """Una fila por trabajador activo con config: su asistencia de ese día (o
    None) + el Δ acumulado del mes hasta esa fecha."""
    configs = list(
        ConfiguracionPlanilla.objects
        .filter(activo=True)
        .select_related("conductor", "ayudante", "usuario")
        .order_by("tipo")
    )
    regs = {
        r.trabajador_id: r
        for r in RegistroAsistencia.objects.filter(trabajador__in=configs, fecha=fecha)
    }
    filas = []
    for c in sorted(configs, key=lambda x: x.nombre.lower()):
        r = regs.get(c.id)
        filas.append({
            "trabajadorId": c.id,
            "workerType": c.tipo,
            "workerName": c.nombre,
            "contractType": c.tipo_contrato,
            "workdayHours": c.horas_jornada,
            "lunchHours": c.horas_refrigerio,
            "attendanceId": r.id if r else None,
            "dayType": r.tipo_dia if r else None,
            "clockIn": r.hora_ingreso.strftime("%H:%M") if r and r.hora_ingreso else None,
            "clockOut": r.hora_salida.strftime("%H:%M") if r and r.hora_salida else None,
            "workedHours": float(r.horas_trabajadas) if r else None,
            "delta": float(r.delta_dia) if r else None,
            "note": r.observacion if r else "",
            "balanceHours": float(saldo_horas(c, fecha)),
        })
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
            base = mes
        elif tipo == Pago.TIPO_QUINCENA:
            base = mes / Decimal("2")
        else:  # adelanto: monto libre
            base = _ZERO
        bruto = _money(base - valor_dia * len(faltas_nc))
        afp = _money(bruto * Decimal(str(trabajador.pct_afp or 0)) / Decimal("100"))

    neto = _money(bruto - afp)
    return {
        "daysWorked": dias_trab,
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
