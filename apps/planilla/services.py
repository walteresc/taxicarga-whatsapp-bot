"""Consultas y helpers del módulo Planilla."""
from datetime import date as _date
from decimal import Decimal

from django.db.models import Q, Sum

from apps.api.filters import apply_active_filter, apply_ordering
from apps.planilla.models import ConfiguracionPlanilla, RegistroAsistencia

_ZERO = Decimal("0")

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
            "monthDelta": float(month_delta(c, fecha)),
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
