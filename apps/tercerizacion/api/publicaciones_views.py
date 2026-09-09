"""API v2 · Publicaciones a transportistas (F3).

    GET  /api/v2/publications/                   lista (filtros: state, search)
    GET  /api/v2/publications/<pk>/              detalle + ofertas + servicio
    POST /api/v2/publications/<pk>/publish       {groups?}
    POST /api/v2/publications/<pk>/offers        {carrierId, vehicleId?, amount, note?}
    POST /api/v2/publications/<pk>/award         {offerId, vehicleId?}
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.pagination import StandardPagination
from apps.api.permissions import HasAnyRole
from apps.tercerizacion import adjudicacion as adj
from apps.tercerizacion.models import (
    OfertaTransportista, PublicacionCarga, Transportista, TransportistaVehiculo,
)

_ROLES = ("Administrador", "Supervisor", "Despacho", "Asesor de Ventas")

_STATE_EN = {
    "borrador": "draft", "abierta": "open", "publicada": "open",
    "con_ofertas": "with_offers", "adjudicada": "awarded",
    "cancelada": "cancelled", "vencida": "expired",
}
_STATE_ES = {"draft": "borrador", "open": "abierta", "with_offers": "con_ofertas",
             "awarded": "adjudicada", "cancelled": "cancelada", "expired": "vencida"}
_PRICE_MODE_EN = {"fijo": "fixed", "referencial": "reference", "abierto": "open"}
_OFFER_STATE_EN = {
    "pendiente": "pending", "contraoferta_taxicarga": "countered_us",
    "contraoferta_transportista": "countered_carrier", "aceptada": "accepted",
    "rechazada": "rejected", "retirada": "withdrawn", "vencida": "expired",
}


def _d(dt):
    return dt.isoformat() if dt else None


def _num(v):
    return float(v) if v is not None else None


def _amount(raw, label="monto"):
    if raw in (None, ""):
        raise ValidationError({label: "Ingresá un monto."})
    try:
        v = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        raise ValidationError({label: "Monto no válido."})
    if v <= 0:
        raise ValidationError({label: "El monto debe ser mayor que cero."})
    return v


def publication_item(pub):
    s = pub.servicio
    return {
        "id": pub.id,
        "code": pub.codigo,
        "bookingCode": s.codigo,
        "leadId": s.lead_origen_id,
        "route": f"{s.distrito_origen or '?'} → {s.distrito_destino or '?'}",
        "date": _d(s.fecha_servicio),
        "state": _STATE_EN.get(pub.estado, pub.estado),
        "priceMode": _PRICE_MODE_EN.get(pub.modo_precio, pub.modo_precio),
        "publishedPrice": _num(pub.precio_publicado),
        "offerCount": pub.ofertas.exclude(estado="rechazada").count(),
        "publishedAt": _d(pub.publicada_en),
        "awardedAt": _d(pub.adjudicada_en),
        "createdAt": _d(pub.creado_en),
    }


def offer_item(o):
    carrier = o.transportista
    return {
        "id": o.id,
        "carrierId": o.transportista_id,
        "carrierName": carrier.nombre if carrier else (o.cliente.nombre if o.cliente else "Contacto WhatsApp"),
        "affiliated": o.transportista_id is not None,
        "vehicleId": o.transportista_vehiculo_id,
        "vehiclePlate": o.transportista_vehiculo.placa if o.transportista_vehiculo_id else None,
        "firstAmount": _num(o.precio_ofertado),
        "currentAmount": _num(o.monto_actual or o.precio_ofertado),
        "state": _OFFER_STATE_EN.get(o.estado, o.estado),
        "acceptedAt": _d(o.fecha_aceptacion),
        "createdAt": _d(o.creado_en),
    }


def publication_detail(pub):
    out = publication_item(pub)
    s = pub.servicio
    out["service"] = {
        "code": s.codigo,
        "origin": s.distrito_origen,
        "destination": s.distrito_destino,
        "date": _d(s.fecha_servicio),
        "schedule": s.horario_servicio,
        "cargo": s.detalle_carga,
        "salePrice": _num(s.precio),
    }
    out["publishedText"] = pub.texto_publicado
    out["groups"] = pub.grupos_publicados or []
    out["offers"] = [offer_item(o) for o in pub.ofertas.select_related(
        "transportista", "transportista_vehiculo", "cliente",
    ).order_by("monto_actual", "creado_en")]
    out["winningOfferId"] = pub.oferta_ganadora_id
    return out


class _Base(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler


_PUB_QS = PublicacionCarga.objects.select_related(
    "servicio", "servicio__lead_origen", "oferta_ganadora",
).prefetch_related("ofertas")


class PublicationListView(_Base):
    def get(self, request):
        p = request.query_params
        qs = _PUB_QS
        st = _STATE_ES.get(p.get("state"))
        if st:
            qs = qs.filter(estado=st)
        elif p.get("active") == "true":
            qs = qs.filter(estado__in=["borrador", "abierta", "publicada", "con_ofertas"])
        search = (p.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(codigo__icontains=search)
                | Q(servicio__codigo__icontains=search)
                | Q(servicio__distrito_origen__icontains=search)
                | Q(servicio__distrito_destino__icontains=search)
            )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.order_by("-creado_en"), request, view=self)
        return paginator.get_paginated_response([publication_item(x) for x in page])


class PublicationDetailView(_Base):
    def get(self, request, pk):
        return Response(publication_detail(get_object_or_404(_PUB_QS, pk=pk)))


class PublicationPublishView(_Base):
    def post(self, request, pk):
        pub = get_object_or_404(_PUB_QS, pk=pk)
        groups = request.data.get("groups") or []
        if isinstance(groups, str):
            groups = [g.strip() for g in groups.split(",") if g.strip()]
        try:
            adj.publicar_publicacion(pub, request.user, grupos=groups)
        except adj.AdjudicacionError as e:
            raise ValidationError(str(e))
        return Response(publication_detail(get_object_or_404(_PUB_QS, pk=pk)))


class PublicationOffersView(_Base):
    def post(self, request, pk):
        pub = get_object_or_404(_PUB_QS, pk=pk)
        d = request.data
        carrier = get_object_or_404(Transportista, pk=d.get("carrierId"))
        vehiculo = None
        if d.get("vehicleId"):
            vehiculo = get_object_or_404(
                TransportistaVehiculo, pk=d["vehicleId"], transportista=carrier,
            )
        amount = _amount(d.get("amount"))
        try:
            adj.registrar_oferta(
                pub, monto=amount, usuario=request.user, transportista=carrier,
                transportista_vehiculo=vehiculo, nota=(d.get("note") or "").strip(),
            )
        except adj.AdjudicacionError as e:
            raise ValidationError(str(e))
        return Response(publication_detail(get_object_or_404(_PUB_QS, pk=pk)))


class PublicationAwardView(_Base):
    def post(self, request, pk):
        pub = get_object_or_404(_PUB_QS, pk=pk)
        oferta = get_object_or_404(OfertaTransportista, pk=request.data.get("offerId"), publicacion=pub)
        vehiculo = None
        if request.data.get("vehicleId"):
            vehiculo = get_object_or_404(
                TransportistaVehiculo, pk=request.data["vehicleId"],
            )
        try:
            prog = adj.adjudicar_publicacion(pub, oferta, request.user, transportista_vehiculo=vehiculo)
        except adj.AdjudicacionError as e:
            raise ValidationError(str(e))
        return Response({
            "ok": True,
            "assignmentId": prog.id,
            "publication": publication_detail(get_object_or_404(_PUB_QS, pk=pk)),
        })
