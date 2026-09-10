"""API v2 · Liquidaciones de tercerización (P1) — vista de Finanzas.

    GET  /api/v2/settlements/                lista (state, carrier, from, to, search)
    GET  /api/v2/settlements/summary         totales
    GET  /api/v2/settlements/<pk>/           detalle
    PATCH /api/v2/settlements/<pk>/          {collectionMethod?}
    POST /api/v2/settlements/<pk>/settle     {reference?, date?, receipt?, note?}
    POST /api/v2/settlements/<pk>/void       {reason?}
"""
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.pagination import StandardPagination
from apps.api.permissions import HasAnyRole
from apps.tercerizacion import liquidaciones as liq_svc
from apps.tercerizacion.models import Liquidacion

_ROLES = ("Administrador", "Gerencia", "Finanzas", "Despacho")


def _d(v):
    return v.isoformat() if v else None


def _num(v):
    return float(v) if v is not None else None


def item(liq):
    s = liq.servicio
    return {
        "id": liq.id,
        "serviceCode": s.codigo,
        "route": f"{s.distrito_origen or '?'} → {s.distrito_destino or '?'}",
        "date": _d(s.fecha_servicio),
        "carrierId": liq.transportista_id,
        "carrierName": liq.transportista.nombre,
        "servicePrice": _num(liq.precio_servicio),
        "carrierCost": _num(liq.costo_transportista),
        "commissionPct": _num(liq.comision_pct),
        "commission": _num(liq.comision_monto),
        "noCommission": liq.sin_comision,
        "exemptionReason": liq.exencion_motivo,
        "net": _num(liq.neto),
        "direction": liq.direccion,
        "collectionMethod": liq.medio_cobro_cliente,
        "state": liq.estado,
        "settledOn": _d(liq.fecha_liquidacion),
        "paymentRef": liq.referencia_pago,
        "createdAt": _d(liq.creado_en),
    }


class _Base(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler


_QS = Liquidacion.objects.select_related("servicio", "transportista", "programacion")


class SettlementListView(_Base):
    def get(self, request):
        p = request.query_params
        qs = _QS
        if p.get("state"):
            qs = qs.filter(estado=p["state"])
        if p.get("carrier"):
            qs = qs.filter(transportista_id=p["carrier"])
        if p.get("method"):
            qs = qs.filter(medio_cobro_cliente=p["method"])
        if p.get("from"):
            qs = qs.filter(servicio__fecha_servicio__gte=p["from"])
        if p.get("to"):
            qs = qs.filter(servicio__fecha_servicio__lte=p["to"])
        search = (p.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(servicio__codigo__icontains=search)
                | Q(transportista__nombre__icontains=search)
                | Q(referencia_pago__icontains=search)
            )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.order_by("-creado_en"), request, view=self)
        return paginator.get_paginated_response([item(x) for x in page])


class SettlementSummaryView(_Base):
    def get(self, request):
        qs = _QS.exclude(estado=Liquidacion.ESTADO_ANULADA)
        pendientes = qs.exclude(estado=Liquidacion.ESTADO_PAGADA)
        a_pagar = pendientes.filter(neto__gt=0).aggregate(s=Sum("neto"))["s"] or 0
        a_cobrar = pendientes.filter(neto__lt=0).aggregate(s=Sum("neto"))["s"] or 0
        liquidado = qs.filter(estado=Liquidacion.ESTADO_PAGADA).aggregate(s=Sum("neto"))["s"] or 0
        comision_pend = pendientes.aggregate(s=Sum("comision_monto"))["s"] or 0
        return Response({
            "toPayCarriers": _num(a_pagar),
            "toCollectFromCarriers": _num(abs(a_cobrar)),
            "settledNet": _num(liquidado),
            "pendingCommission": _num(comision_pend),
            "pendingCount": pendientes.count(),
        })


class SettlementDetailView(_Base):
    def get(self, request, pk):
        return Response(item(get_object_or_404(_QS, pk=pk)))

    def patch(self, request, pk):
        liq = get_object_or_404(_QS, pk=pk)
        if liq.estado in (Liquidacion.ESTADO_PAGADA, Liquidacion.ESTADO_ANULADA):
            raise ValidationError("La liquidación ya está cerrada.")
        d = request.data
        if "noCommission" in d:
            s = liq.servicio
            s.sin_comision = bool(d["noCommission"])
            s.sin_comision_motivo = (d.get("exemptionReason") or "").strip()
            s.save(update_fields=["sin_comision", "sin_comision_motivo"])
            liq_svc.recalcular(liq)
            liq.refresh_from_db()
        if "collectionMethod" in d:
            liq_svc.set_medio_cobro(liq, d["collectionMethod"], usuario=request.user)
        return Response(item(get_object_or_404(_QS, pk=pk)))


class SettlementSettleView(_Base):
    def post(self, request, pk):
        liq = get_object_or_404(_QS, pk=pk)
        d = request.data
        fecha = None
        if d.get("date"):
            try:
                fecha = datetime.strptime(d["date"][:10], "%Y-%m-%d").date()
            except ValueError:
                raise ValidationError({"date": "Fecha no válida (AAAA-MM-DD)."})
        liq_svc.marcar_liquidada(
            liq, usuario=request.user,
            referencia=(d.get("reference") or "").strip(),
            fecha=fecha, comprobante=(d.get("receipt") or "").strip(),
            nota=(d.get("note") or "").strip(),
        )
        return Response(item(get_object_or_404(_QS, pk=pk)))


class SettlementVoidView(_Base):
    permission_classes = [HasAnyRole("Administrador", "Gerencia", "Finanzas")]

    def post(self, request, pk):
        liq = get_object_or_404(_QS, pk=pk)
        liq_svc.anular_liquidacion(liq, usuario=request.user, motivo=(request.data.get("reason") or "").strip())
        return Response(item(get_object_or_404(_QS, pk=pk)))
