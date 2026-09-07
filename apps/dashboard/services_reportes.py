"""Capa de cálculo para las pantallas de Reportes.

Dos fuentes de datos distintas y disjuntas (ver docs/REPORTES-VENTAS.md):

- **Benchmark histórico**: `cotizador.ServicioHistorico` (~19.5k filas importadas de
  la hoja "wally"). Llega hasta jul-2026, no crece con la operación, no es
  atribuible a asesor ni canal. Sirve para ver la tendencia del negocio y para
  tarifar rutas interprovinciales.
- **Ventas vivas**: `servicios.Servicio` + `leads.Lead` + `servicios.PagoReserva` +
  `cotizador.CotizacionComercial`. Atribuible y completo, pero se llena solo con el
  uso del CRM. Todas las funciones devuelven ceros (no excepción) con la base vacía.

Nada aquí escribe en la base. Nada toca el chat en tiempo real.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from statistics import median

from django.db.models import (
    Avg, Count, DecimalField, F, Q, Sum, Value,
)
from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncWeek, TruncYear
from django.utils import timezone

from apps.cotizador.models import CotizacionComercial, ServicioHistorico
from apps.leads.models import Lead
from apps.servicios.models import (
    PagoReserva, Servicio,
    SERVICIO_CANCELADO, SERVICIO_FINALIZADO,
)
from apps.whatsapp.services_extraccion import _CIUDADES_NO_LIMA, _menciona_ciudad_no_lima

_CERO = Decimal("0.00")
_DEC = DecimalField(max_digits=14, decimal_places=2)

# Estados de CotizacionComercial que cuentan como "cotización enviada al cliente".
COTIZACION_ENVIADA_ESTADOS = (
    "enviada", "entregada", "en_negociacion", "aceptada", "rechazada",
)


# --------------------------------------------------------------------------- #
#  Utilidades
# --------------------------------------------------------------------------- #

def _pct(parte, total):
    if not total:
        return 0.0
    return round(100.0 * parte / total, 1)


def _ratio(num, den):
    if not den:
        return 0.0
    return round(100.0 * num / den, 1)


def _percentiles(valores):
    """mediana / p25 / p75 / p90 de una lista de números. Robusto ante listas
    cortas o vacías (devuelve ceros)."""
    xs = sorted(float(v) for v in valores if v is not None)
    if not xs:
        return {"n": 0, "min": 0.0, "p25": 0.0, "mediana": 0.0, "p75": 0.0, "p90": 0.0, "max": 0.0}
    n = len(xs)

    def q(p):
        if n == 1:
            return xs[0]
        idx = min(int(round(p * (n - 1))), n - 1)
        return xs[idx]

    return {
        "n": n,
        "min": round(xs[0], 2),
        "p25": round(q(0.25), 2),
        "mediana": round(median(xs), 2),
        "p75": round(q(0.75), 2),
        "p90": round(q(0.90), 2),
        "max": round(xs[-1], 2),
    }


def _ruta_fuera_de_lima(origen, destino):
    return _menciona_ciudad_no_lima(f"{origen or ''} {destino or ''}")


_CIUDADES_ORDENADAS = sorted(_CIUDADES_NO_LIMA, key=len, reverse=True)
_CIUDAD_ALIAS = {
    "cuzco": "Cusco", "canete": "Cañete", "nasca": "Nazca", "huanuco": "Huánuco",
}


def _ciudad_no_lima(texto):
    """Primera ciudad de provincia mencionada en el texto, o 'Lima'."""
    t = (texto or "").lower()
    for ciudad in _CIUDADES_ORDENADAS:
        if ciudad in t:
            return _CIUDAD_ALIAS.get(ciudad, ciudad.title())
    return "Lima"


def _clave_ruta_interprovincial(origen, destino):
    """Normaliza una ruta a 'CiudadA ↔ CiudadB' para agrupar direcciones sucias
    ('Chincha alta(pedir al cliente)' y 'chincha alta' caen en la misma)."""
    a, b = _ciudad_no_lima(origen), _ciudad_no_lima(destino)
    return " ↔ ".join(sorted({a, b})) if a != b else a


def rango_por_defecto():
    """Últimos 90 días, terminando hoy."""
    hoy = timezone.localdate()
    return hoy - dt.timedelta(days=90), hoy


def parse_rango(desde_str, hasta_str, periodo, ancla_str=None):
    """Devuelve (desde, hasta) como date, a partir de los parámetros del filtro.

    periodo: 'dia' | 'semana' | 'quincena' | 'mes' | 'rango'.
    Para todo lo que no sea 'rango', se usa `ancla` (o hoy) para calcular el
    periodo que la contiene.
    """
    hoy = timezone.localdate()

    def _d(s):
        try:
            return dt.date.fromisoformat(s)
        except (TypeError, ValueError):
            return None

    if periodo == "rango":
        desde = _d(desde_str) or (hoy - dt.timedelta(days=30))
        hasta = _d(hasta_str) or hoy
        if hasta < desde:
            desde, hasta = hasta, desde
        return desde, hasta

    ancla = _d(ancla_str) or hoy
    if periodo == "dia":
        return ancla, ancla
    if periodo == "semana":
        lunes = ancla - dt.timedelta(days=ancla.weekday())
        return lunes, lunes + dt.timedelta(days=6)
    if periodo == "quincena":
        if ancla.day <= 15:
            return ancla.replace(day=1), ancla.replace(day=15)
        fin = (ancla.replace(day=1) + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
        return ancla.replace(day=16), fin
    # mes (por defecto)
    inicio = ancla.replace(day=1)
    fin = (inicio + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    return inicio, fin


def _trunc_para(agrupacion):
    return {
        "dia": TruncDay, "semana": TruncWeek, "mes": TruncMonth, "anio": TruncYear,
    }.get(agrupacion, TruncMonth)


def _aplicar_filtros_servicio(qs, filtros):
    if filtros.get("asesor_id"):
        qs = qs.filter(asesor_id=filtros["asesor_id"])
    if filtros.get("canal_id"):
        qs = qs.filter(whatsapp_channel_id=filtros["canal_id"])
    if filtros.get("tipo"):
        qs = qs.filter(tipo_servicio__iexact=filtros["tipo"])
    return qs


def _monto_servicio():
    """precio_final -> precio -> precio_cotizado -> 0, como expresión SQL."""
    return Coalesce("precio_final", "precio", "precio_cotizado", Value(_CERO), output_field=_DEC)


# --------------------------------------------------------------------------- #
#  PANTALLA 1 — Benchmark histórico
# --------------------------------------------------------------------------- #

def benchmark_historico():
    qs = ServicioHistorico.objects.all()
    total = qs.count()

    por_anio = list(
        qs.annotate(a=TruncYear("fecha"))
        .values("a")
        .annotate(n=Count("id"), cerrados=Count("id", filter=Q(cerrado=True)))
        .order_by("a")
    )
    por_mes = list(
        qs.filter(fecha__gte=dt.date(2023, 1, 1))
        .annotate(m=TruncMonth("fecha"))
        .values("m")
        .annotate(n=Count("id"))
        .order_by("m")
    )
    por_tipo = list(
        qs.values("tipo_servicio")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    for row in por_tipo:
        row["pct"] = _pct(row["n"], total)

    def _barpct(filas, campo="n"):
        mx = max((f[campo] for f in filas), default=0) or 1
        for f in filas:
            f["barpct"] = round(100.0 * f[campo] / mx, 1)

    _barpct(por_anio)
    _barpct(por_mes)
    _barpct(por_tipo)

    # Distribución de precio y split local/interprovincial: un solo recorrido.
    cerrados = qs.filter(cerrado=True).values_list(
        "distrito_origen", "distrito_destino", "tipo_servicio",
        "precio_final", "precio_cotizado",
    )
    precios_todos, precios_local, precios_inter = [], [], []
    suma_local = suma_inter = _CERO
    rutas_inter: dict[tuple[str, str], list[float]] = {}
    for origen, destino, tipo, pf, pc in cerrados.iterator():
        precio = pf if pf is not None else pc
        if precio is None or precio <= 0:
            continue
        precio_f = float(precio)
        precios_todos.append(precio_f)
        if _ruta_fuera_de_lima(origen, destino):
            precios_inter.append(precio_f)
            suma_inter += Decimal(str(precio))
            rutas_inter.setdefault(_clave_ruta_interprovincial(origen, destino), []).append(precio_f)
        else:
            precios_local.append(precio_f)
            suma_local += Decimal(str(precio))

    n_local, n_inter = len(precios_local), len(precios_inter)
    fact_total = float(suma_local + suma_inter) or 1.0

    ambito = {
        "local": {
            "n": n_local, "pct_servicios": _pct(n_local, n_local + n_inter),
            "ticket_promedio": round(sum(precios_local) / n_local, 2) if n_local else 0.0,
            "mediana": round(median(precios_local), 2) if precios_local else 0.0,
            "facturacion": round(float(suma_local), 2),
            "pct_facturacion": _pct(float(suma_local), fact_total),
        },
        "interprovincial": {
            "n": n_inter, "pct_servicios": _pct(n_inter, n_local + n_inter),
            "ticket_promedio": round(sum(precios_inter) / n_inter, 2) if n_inter else 0.0,
            "mediana": round(median(precios_inter), 2) if precios_inter else 0.0,
            "facturacion": round(float(suma_inter), 2),
            "pct_facturacion": _pct(float(suma_inter), fact_total),
        },
    }

    rutas_frecuentes = sorted(
        (
            {
                "ruta": ruta, "casos": len(precios),
                "precio_tipico": round(median(precios), 2),
                "precio_min": round(min(precios), 2),
                "precio_max": round(max(precios), 2),
            }
            for ruta, precios in rutas_inter.items()
            if len(precios) >= 3
        ),
        key=lambda r: (-r["casos"], -r["precio_tipico"]),
    )

    fecha_min = qs.order_by("fecha").values_list("fecha", flat=True).first()
    fecha_max = qs.order_by("-fecha").values_list("fecha", flat=True).first()

    return {
        "total": total,
        "cerrados": len(precios_todos),
        "fecha_min": fecha_min,
        "fecha_max": fecha_max,
        "por_anio": por_anio,
        "por_mes": por_mes,
        "por_tipo": por_tipo,
        "precio": {
            "todos": _percentiles(precios_todos),
            "local": _percentiles(precios_local),
            "interprovincial": _percentiles(precios_inter),
        },
        "ambito": ambito,
        "rutas_interprovinciales": rutas_frecuentes,
    }


# --------------------------------------------------------------------------- #
#  PANTALLA 2 — Ventas vivas
# --------------------------------------------------------------------------- #

def ventas_por_periodo(desde, hasta, *, agrupacion="mes", filtros=None):
    filtros = filtros or {}
    base = Servicio.objects.filter(
        fecha_confirmacion__gte=desde, fecha_confirmacion__lte=hasta
    )
    base = _aplicar_filtros_servicio(base, filtros)

    trunc = _trunc_para(agrupacion)
    monto = _monto_servicio()

    def _resumen(qs):
        agg = qs.aggregate(
            n=Count("id"),
            total=Coalesce(Sum(monto), Value(_CERO), output_field=_DEC),
        )
        n = agg["n"] or 0
        total = agg["total"] or _CERO
        return {
            "n": n,
            "facturado": round(float(total), 2),
            "ticket_promedio": round(float(total) / n, 2) if n else 0.0,
        }

    bruto = _resumen(base)
    neto = _resumen(base.exclude(estado=SERVICIO_CANCELADO))
    cancelados = base.filter(estado=SERVICIO_CANCELADO).count()

    serie = list(
        base.exclude(estado=SERVICIO_CANCELADO)
        .annotate(bucket=trunc("fecha_confirmacion"))
        .values("bucket")
        .annotate(
            n=Count("id"),
            facturado=Coalesce(Sum(monto), Value(_CERO), output_field=_DEC),
        )
        .order_by("bucket")
    )
    for row in serie:
        row["facturado"] = round(float(row["facturado"]), 2)

    por_asesor = _desglose(base, "asesor__username", "asesor_id", monto)
    por_canal = _desglose(base, "whatsapp_channel__nombre", "whatsapp_channel_id", monto)
    por_tipo = _desglose(base, "tipo_servicio", "tipo_servicio", monto)

    return {
        "desde": desde, "hasta": hasta, "agrupacion": agrupacion,
        "bruto": bruto, "neto": neto, "cancelados": cancelados,
        "serie": serie,
        "por_asesor": por_asesor,
        "por_canal": por_canal,
        "por_tipo": por_tipo,
    }


def _desglose(base_qs, campo_label, campo_group, monto):
    qs = (
        base_qs.exclude(estado=SERVICIO_CANCELADO)
        .values(campo_group, campo_label)
        .annotate(
            n=Count("id"),
            facturado=Coalesce(Sum(monto), Value(_CERO), output_field=_DEC),
        )
        .order_by("-facturado")
    )
    filas = []
    for row in qs:
        n = row["n"] or 0
        fac = float(row["facturado"] or 0)
        filas.append({
            "clave": row.get(campo_group),
            "label": row.get(campo_label) or "— sin asignar —",
            "n": n,
            "facturado": round(fac, 2),
            "ticket_promedio": round(fac / n, 2) if n else 0.0,
        })
    return filas


def embudo_conversion(desde, hasta, *, filtros=None):
    filtros = filtros or {}
    leads = Lead.objects.filter(fecha_creacion__date__gte=desde, fecha_creacion__date__lte=hasta)
    if filtros.get("canal_id"):
        leads = leads.filter(whatsapp_channel_id=filtros["canal_id"])
    if filtros.get("asesor_id"):
        leads = leads.filter(vendedor_asignado_id=filtros["asesor_id"])
    if filtros.get("tipo"):
        leads = leads.filter(tipo_servicio__iexact=filtros["tipo"])

    creados = leads.count()

    cot_qs = CotizacionComercial.objects.filter(
        creada_en__date__gte=desde, creada_en__date__lte=hasta,
        estado__in=COTIZACION_ENVIADA_ESTADOS,
    )
    if filtros.get("canal_id"):
        cot_qs = cot_qs.filter(channel_id=filtros["canal_id"])
    if filtros.get("asesor_id"):
        cot_qs = cot_qs.filter(asesor_id=filtros["asesor_id"])
    cotizados = cot_qs.values("lead_id").distinct().count()

    ganados = leads.filter(estado=Lead.CERRADO).count()
    perdidos = leads.filter(estado=Lead.PERDIDO).count()

    motivos = list(
        leads.filter(estado=Lead.PERDIDO)
        .values("motivo_perdida")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    etiquetas = dict(Lead.MOTIVOS_PERDIDA)
    for m in motivos:
        m["label"] = etiquetas.get(m["motivo_perdida"], m["motivo_perdida"] or "— sin motivo —")

    ciclo_dias = (
        leads.filter(estado__in=[Lead.CERRADO, Lead.PERDIDO], fecha_cierre__isnull=False)
        .annotate(dias=F("fecha_cierre") - F("fecha_creacion"))
        .values_list("dias", flat=True)
    )
    dias = [d.days for d in ciclo_dias if d is not None]

    return {
        "desde": desde, "hasta": hasta,
        "creados": creados,
        "cotizados": cotizados,
        "ganados": ganados,
        "perdidos": perdidos,
        "tasa_cotizacion": _ratio(cotizados, creados),
        "tasa_cierre": _ratio(ganados, cotizados),
        "win_rate": _ratio(ganados, ganados + perdidos),
        "ciclo_promedio_dias": round(sum(dias) / len(dias), 1) if dias else 0.0,
        "ciclo_mediana_dias": round(median(dias), 1) if dias else 0.0,
        "motivos_perdida": motivos,
    }


def ticket_local_interprovincial(desde, hasta, *, filtros=None):
    filtros = filtros or {}
    base = Servicio.objects.filter(
        fecha_confirmacion__gte=desde, fecha_confirmacion__lte=hasta,
    ).exclude(estado=SERVICIO_CANCELADO)
    base = _aplicar_filtros_servicio(base, filtros)
    monto = _monto_servicio()

    def _bloque(qs):
        agg = qs.aggregate(
            n=Count("id"),
            total=Coalesce(Sum(monto), Value(_CERO), output_field=_DEC),
        )
        n = agg["n"] or 0
        total = float(agg["total"] or 0)
        return {"n": n, "facturado": round(total, 2),
                "ticket_promedio": round(total / n, 2) if n else 0.0}

    inter = _bloque(base.filter(es_interprovincial=True))
    local = _bloque(base.filter(es_interprovincial=False))
    total_n = inter["n"] + local["n"]
    total_fac = inter["facturado"] + local["facturado"]
    for blk in (inter, local):
        blk["pct_servicios"] = _pct(blk["n"], total_n)
        blk["pct_facturacion"] = _pct(blk["facturado"], total_fac)

    return {"desde": desde, "hasta": hasta, "local": local, "interprovincial": inter}


def cobranzas(desde, hasta, *, filtros=None):
    filtros = filtros or {}
    servicios = Servicio.objects.filter(
        fecha_confirmacion__gte=desde, fecha_confirmacion__lte=hasta,
    ).exclude(estado=SERVICIO_CANCELADO)
    servicios = _aplicar_filtros_servicio(servicios, filtros)

    facturado = cobrado = pendiente = _CERO
    por_estado = {"pagado": 0, "amortizado": 0, "pendiente": 0, "sin_precio": 0}
    antiguedad = {"d0_7": _CERO, "d8_30": _CERO, "d31_mas": _CERO}
    top_pendientes = []
    hoy = timezone.localdate()

    for s in servicios.select_related("cliente").iterator():
        precio = s.precio or _CERO
        pagado = s.total_pagado
        saldo = s.saldo_pendiente
        facturado += precio
        cobrado += pagado
        pendiente += saldo
        por_estado[s.estado_pago] = por_estado.get(s.estado_pago, 0) + 1
        if saldo > 0:
            ref = s.fecha_servicio or s.fecha_confirmacion or hoy
            edad = (hoy - ref).days
            bucket = "d0_7" if edad <= 7 else ("d8_30" if edad <= 30 else "d31_mas")
            antiguedad[bucket] += saldo
            top_pendientes.append({
                "codigo": s.codigo,
                "cliente": (s.cliente.nombre if s.cliente else "—"),
                "saldo": round(float(saldo), 2),
                "dias": max(edad, 0),
            })

    # Cobrado por método de pago (sobre pagos reales del periodo de confirmación).
    metodos = list(
        PagoReserva.objects.filter(
            servicio__in=servicios, concepto__in=["adelanto", "parcial", "final"],
        )
        .values("metodo_pago")
        .annotate(total=Coalesce(Sum("monto"), Value(_CERO), output_field=_DEC), n=Count("id"))
        .order_by("-total")
    )
    etiquetas_metodo = dict(getattr(PagoReserva._meta.get_field("metodo_pago"), "choices", []))
    for m in metodos:
        m["label"] = etiquetas_metodo.get(m["metodo_pago"], m["metodo_pago"])
        m["total"] = round(float(m["total"]), 2)

    top_pendientes.sort(key=lambda r: -r["saldo"])

    return {
        "desde": desde, "hasta": hasta,
        "facturado": round(float(facturado), 2),
        "cobrado": round(float(cobrado), 2),
        "pendiente": round(float(pendiente), 2),
        "pct_cobrado": _pct(float(cobrado), float(facturado) or 1.0),
        "por_estado_pago": por_estado,
        "antiguedad_saldo": {k: round(float(v), 2) for k, v in antiguedad.items()},
        "metodos_pago": metodos,
        "top_pendientes": top_pendientes[:15],
    }


# --------------------------------------------------------------------------- #
#  Opciones para los filtros
# --------------------------------------------------------------------------- #

def opciones_filtro():
    from django.contrib.auth import get_user_model
    from apps.whatsapp.models import WhatsAppChannel

    User = get_user_model()
    asesores = list(
        User.objects.filter(is_active=True)
        .filter(Q(servicios_asesorados__isnull=False) | Q(leads_asignados__isnull=False))
        .distinct()
        .values("id", "username", "first_name", "last_name")
        .order_by("first_name", "username")
    )
    if not asesores:
        asesores = list(
            User.objects.filter(is_active=True)
            .values("id", "username", "first_name", "last_name")
            .order_by("first_name", "username")[:50]
        )
    canales = list(WhatsAppChannel.objects.values("id", "nombre").order_by("nombre"))
    tipos = list(
        Servicio.objects.exclude(tipo_servicio="")
        .values_list("tipo_servicio", flat=True).distinct().order_by("tipo_servicio")
    )
    if not tipos:
        tipos = ["carga", "mudanza", "oficina"]
    return {"asesores": asesores, "canales": canales, "tipos": tipos}
