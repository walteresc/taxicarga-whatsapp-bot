"""API v2 de Reportes. Envoltorio fino sobre `services_reportes` (reutilizado tal
cual); solo traduce las claves al inglés. Solo lectura, sin paginación.

    GET /api/v2/reports/benchmark
    GET /api/v2/reports/sales?period=day|week|fortnight|month|range&from=&to=&on=&advisor=&channel=&type=

Acceso: Analítica es un módulo de Gerencia/Despacho/Finanzas — a propósito
SIN Supervisor (decisión del usuario, 2026-09-12: Supervisor ve todo el
flujo operativo pero no Finanzas/Analítica/Configuración).
"""
import datetime as dt

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.permissions import HasAnyRole
from apps.dashboard import services_reportes as R

from .reports_mappers import rename

_ROLES = ("Administrador", "Gerencia", "Despacho", "Finanzas")

_PERIOD_ES = {
    "day": "dia", "week": "semana", "fortnight": "quincena",
    "month": "mes", "range": "rango",
}


class BenchmarkReportView(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get(self, request):
        return Response(rename(R.benchmark_historico()))


class SalesReportView(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get(self, request):
        qp = request.query_params
        period_es = _PERIOD_ES.get(qp.get("period"), "mes")
        desde, hasta = R.parse_rango(qp.get("from"), qp.get("to"), period_es, qp.get("on"))

        def _int(name):
            v = qp.get(name)
            return int(v) if (v and v.isdigit()) else None

        filtros = {
            "asesor_id": _int("advisor"),
            "canal_id": _int("channel"),
            "tipo": (qp.get("type") or "").strip() or None,
        }

        span = (hasta - desde).days
        agrupacion = "mes" if span > 120 else ("semana" if span > 45 else "dia")

        data = {
            "from": desde,
            "to": hasta,
            "period": qp.get("period") or "month",
            "sales": R.ventas_por_periodo(desde, hasta, agrupacion=agrupacion, filtros=filtros),
            "funnel": R.embudo_conversion(desde, hasta, filtros=filtros),
            "ticket": R.ticket_local_interprovincial(desde, hasta, filtros=filtros),
            "collections": R.cobranzas(desde, hasta, filtros=filtros),
            "filterOptions": R.opciones_filtro(),
        }
        return Response(rename(data))


class OutsourcingReportView(APIView):
    """Propio vs Tercerizado + margen (F8). Expone el costo de compra. Usa
    `_ROLES` (Analítica, sin Supervisor) y no el `ROLES_MARGEN` compartido con
    Negociaciones — ahí Supervisor sí sigue viendo el margen porque es parte
    del flujo operativo que conserva, no de este módulo de reportes."""
    permission_classes = [HasAnyRole(*_ROLES)]

    def get(self, request):
        qp = request.query_params
        period_es = _PERIOD_ES.get(qp.get("period"), "mes")
        desde, hasta = R.parse_rango(qp.get("from"), qp.get("to"), period_es, qp.get("on"))
        span = (hasta - desde).days
        agrupacion = "mes" if span > 120 else ("semana" if span > 45 else "dia")
        data = R.propio_vs_tercerizado(desde, hasta, agrupacion=agrupacion)
        data["period"] = qp.get("period") or "month"
        return Response(rename(data))
