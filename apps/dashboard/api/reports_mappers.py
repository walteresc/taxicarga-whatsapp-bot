"""Traducción ES→EN de la salida de `apps.dashboard.services_reportes`.

La capa de cálculo (`services_reportes.py`) se reutiliza tal cual: solo se
renombran las claves del dict de salida al inglés canónico de la API v2. Un único
diccionario `KEYS` + un renombrador recursivo (las estructuras son dicts planos y
listas de dicts planos).
"""

# clave del modelo/servicio (ES)  ->  clave API (EN, camelCase)
KEYS = {
    # comunes
    "n": "count", "pct": "pct", "label": "label", "clave": "key",
    "desde": "from", "hasta": "to",
    "mediana": "median", "min": "min", "max": "max", "p25": "p25", "p75": "p75", "p90": "p90",
    "barpct": "barPct",
    # benchmark
    "total": "total", "cerrados": "closed", "fecha_min": "dateMin", "fecha_max": "dateMax",
    "por_anio": "byYear", "por_mes": "byMonth", "por_tipo": "byType",
    "precio": "price", "todos": "all", "local": "local", "interprovincial": "interprovincial",
    "ambito": "scope", "rutas_interprovinciales": "interprovincialRoutes",
    "a": "date", "m": "date", "tipo_servicio": "type",
    "pct_servicios": "servicesPct", "ticket_promedio": "averageTicket",
    "facturacion": "revenue", "pct_facturacion": "revenuePct",
    "ruta": "route", "casos": "cases", "precio_tipico": "typicalPrice",
    "precio_min": "priceMin", "precio_max": "priceMax",
    # ventas
    "agrupacion": "groupBy", "bruto": "gross", "neto": "net", "cancelados": "cancelled",
    "serie": "series", "por_asesor": "byAdvisor", "por_canal": "byChannel",
    "bucket": "bucket", "facturado": "billed",
    # embudo
    "creados": "created", "cotizados": "quoted", "ganados": "won", "perdidos": "lost",
    "tasa_cotizacion": "quoteRate", "tasa_cierre": "closeRate", "win_rate": "winRate",
    "ciclo_promedio_dias": "avgCycleDays", "ciclo_mediana_dias": "medianCycleDays",
    "motivos_perdida": "lossReasons", "motivo_perdida": "reason",
    # cobranzas
    "cobrado": "collected", "pendiente": "pending", "pct_cobrado": "collectedPct",
    "por_estado_pago": "byPaymentState", "antiguedad_saldo": "balanceAging",
    "metodos_pago": "paymentMethods", "top_pendientes": "topPending",
    "codigo": "code", "cliente": "customer", "saldo": "balance", "dias": "days",
    "metodo_pago": "method",
    "pagado": "paid", "amortizado": "partial", "sin_precio": "noPrice",
    # propio vs tercerizado (F8) — la mayoría de claves ya vienen en inglés
    "resumen": "summary", "serie": "series",
    "total_facturado": "totalRevenue", "margen_tercerizado": "outsourcedMargin",
    # opciones de filtro
    "asesores": "advisors", "canales": "channels", "tipos": "types",
    "id": "id", "username": "username", "first_name": "firstName", "last_name": "lastName",
    "nombre": "name",
}


def rename(value):
    if isinstance(value, dict):
        return {KEYS.get(k, k): rename(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rename(v) for v in value]
    return value
