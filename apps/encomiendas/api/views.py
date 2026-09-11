"""API v2 · Encomiendas (P1).

CRM:
    GET/POST /api/v2/shipments/                lista / alta
    POST     /api/v2/shipments/quote           cotización sin crear
    GET      /api/v2/shipments/zones           zonas + niveles (para el form)
    GET      /api/v2/shipments/<code>/
    POST     /api/v2/shipments/<code>/assign   {carrierId, vehicleId?}
    POST     /api/v2/shipments/<code>/events   {state, detail?, ...}
    POST     /api/v2/shipments/<code>/cancel   {reason?}

Portal del transportista:
    GET  /api/v2/portal/carrier/deliveries
    POST /api/v2/portal/carrier/deliveries/<code>/event   {state, detail?, receivedBy?, failReason?}

Público:
    GET /api/v2/track/<token>
"""
from datetime import datetime

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.pagination import StandardPagination
from apps.api.permissions import HasAnyRole, IsCarrier, carrier_for
from apps.encomiendas import services
from apps.encomiendas.models import Envio, PuntoEntregaDestino, RendicionCaja, RutaReparto, ZonaReparto
from apps.tercerizacion.models import Transportista, TransportistaVehiculo

_ROLES = ("Administrador", "Gerencia", "Supervisor", "Despacho", "Asesor de Ventas")


def _d(v):
    return v.isoformat() if v else None


def _num(v):
    return float(v) if v is not None else None


def item(e):
    return {
        "code": e.codigo,
        "token": e.token,
        "state": e.estado,
        "stateLabel": e.get_estado_display(),
        "level": e.nivel,
        "route": f"{e.origen_distrito} → {e.destino_distrito}",
        "recipient": e.destinatario_nombre,
        "recipientPhone": e.destinatario_telefono,
        "price": _num(e.precio),
        "cod": e.es_contraentrega,
        "codAmount": _num(e.monto_contraentrega),
        "carrierId": e.transportista_id,
        "carrierName": e.transportista.nombre if e.transportista_id else None,
        "createdAt": _d(e.creado_en),
        "deliveredAt": _d(e.entregado_en),
    }


def detail(e):
    out = item(e)
    out.update({
        "sender": {"name": e.remitente_nombre, "phone": e.remitente_telefono,
                   "district": e.origen_distrito, "address": e.origen_direccion, "reference": e.origen_referencia,
                   "lat": _num(e.origen_lat), "lng": _num(e.origen_lng)},
        "recipientFull": {"name": e.destinatario_nombre, "phone": e.destinatario_telefono,
                          "district": e.destino_distrito, "address": e.destino_direccion, "reference": e.destino_referencia,
                          "pickupPoint": e.punto_entrega_destino or None,
                          "lat": _num(e.destino_lat), "lng": _num(e.destino_lng)},
        "package": {"content": e.contenido, "weightKg": _num(e.peso_kg),
                    "lengthCm": e.largo_cm, "widthCm": e.ancho_cm, "heightCm": e.alto_cm,
                    "declaredValue": _num(e.valor_declarado)},
        "carrierVehicleId": e.transportista_vehiculo_id,
        "destinationCarrierId": e.transportista_destino_id,
        "destinationCarrierName": e.transportista_destino.nombre if e.transportista_destino_id else None,
        "routeCode": e.ruta.codigo if e.ruta_id else None,
        "receivedBy": e.recibido_por or None,
        "podPhoto": f"/api/v2/shipments/{e.codigo}/pod-photo" if e.prueba_foto else None,
        "hasSignature": bool(e.prueba_firma),
        "codCollected": _num(e.cod_cobrado), "codMethod": e.cod_medio or None,
        "codToRemit": _num(e.cod_a_remitir), "codHandedOver": e.cod_rendido, "codRemitted": e.cod_remitido,
        "failReason": e.motivo_fallo or None,
        "attempts": e.intentos_entrega,
        "notes": e.notas,
        "events": [
            {"state": ev.estado, "label": dict(Envio.ESTADOS).get(ev.estado, ev.estado),
             "detail": ev.descripcion, "location": ev.ubicacion, "at": _d(ev.creado_en)}
            for ev in e.eventos.all()
        ],
    })
    return out


_FIELD_MAP = {
    "level": "nivel",
    "senderName": "remitente_nombre", "senderPhone": "remitente_telefono",
    "originDistrict": "origen_distrito", "originAddress": "origen_direccion", "originReference": "origen_referencia",
    "recipientName": "destinatario_nombre", "recipientPhone": "destinatario_telefono",
    "destDistrict": "destino_distrito", "destAddress": "destino_direccion", "destReference": "destino_referencia",
    "destPickupPoint": "punto_entrega_destino",
    "originLat": "origen_lat", "originLng": "origen_lng", "destLat": "destino_lat", "destLng": "destino_lng",
    "content": "contenido", "weightKg": "peso_kg", "lengthCm": "largo_cm", "widthCm": "ancho_cm", "heightCm": "alto_cm",
    "declaredValue": "valor_declarado", "cod": "es_contraentrega", "codAmount": "monto_contraentrega",
    "notes": "notas", "price": "precio",
}


class _Base(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler


_QS = Envio.objects.select_related("transportista", "transportista_destino").prefetch_related("eventos")


class ShipmentListView(_Base):
    def get(self, request):
        p = request.query_params
        qs = _QS
        if p.get("state"):
            qs = qs.filter(estado=p["state"])
        if p.get("level"):
            qs = qs.filter(nivel=p["level"])
        if p.get("carrier"):
            qs = qs.filter(transportista_id=p["carrier"])
        if p.get("open") == "true":
            qs = qs.filter(estado__in=Envio.ABIERTOS)
        search = (p.get("search") or "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(codigo__icontains=search) | Q(destinatario_nombre__icontains=search)
                | Q(destinatario_telefono__icontains=search) | Q(destino_direccion__icontains=search)
            )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.order_by("-creado_en"), request, view=self)
        return paginator.get_paginated_response([item(x) for x in page])

    def post(self, request):
        data = {model_f: request.data[api_f] for api_f, model_f in _FIELD_MAP.items() if api_f in request.data}
        for req in ("remitente_nombre", "origen_distrito", "origen_direccion",
                    "destinatario_nombre", "destino_distrito", "destino_direccion"):
            if not str(data.get(req, "")).strip():
                raise ValidationError({req: "Requerido."})
        envio = services.crear_envio(data, usuario=request.user)
        return Response(detail(get_object_or_404(_QS, pk=envio.pk)), status=201)


class ShipmentQuoteView(_Base):
    def get(self, request):
        p = request.query_params
        return Response(services.cotizar(
            origen_distrito=p.get("originDistrict", ""), destino_distrito=p.get("destDistrict", ""),
            nivel=p.get("level") or Envio.NIVEL_EXPRESS, peso_kg=p.get("weightKg") or 1,
        ))


class ShipmentZonesView(_Base):
    def get(self, request):
        return Response({
            "zones": [{"name": z.nombre, "districts": z.distritos}
                      for z in ZonaReparto.objects.filter(activo=True)],
            "levels": [{"value": v, "label": lbl} for v, lbl in Envio.NIVELES],
        })


def _pickup_point_item(p):
    return {
        "id": p.id, "city": p.ciudad, "name": p.nombre, "address": p.direccion,
        "phone": p.telefono, "schedule": p.horario, "active": p.activo,
    }


class PickupPointsView(_Base):
    """Catálogo de puntos de entrega (agencias/afiliados) en ciudades de
    provincia, para encomiendas interprovinciales (Fase A)."""

    def get(self, request):
        qs = PuntoEntregaDestino.objects.all()
        city = (request.query_params.get("city") or "").strip()
        if city:
            qs = qs.filter(ciudad__iexact=city, activo=True)
        return Response({"points": [_pickup_point_item(p) for p in qs]})

    def post(self, request):
        d = request.data
        if not (d.get("city") or "").strip() or not (d.get("name") or "").strip():
            raise ValidationError({"city": "Ciudad y nombre son obligatorios."})
        p = PuntoEntregaDestino.objects.create(
            ciudad=d["city"].strip(), nombre=d["name"].strip(),
            direccion=d.get("address") or "", telefono=d.get("phone") or "",
            horario=d.get("schedule") or "", activo=d.get("active", True),
        )
        return Response(_pickup_point_item(p), status=201)


class PickupPointDetailView(_Base):
    def patch(self, request, pk):
        p = get_object_or_404(PuntoEntregaDestino, pk=pk)
        d = request.data
        for api_f, model_f in (("city", "ciudad"), ("name", "nombre"), ("address", "direccion"),
                                ("phone", "telefono"), ("schedule", "horario")):
            if api_f in d:
                setattr(p, model_f, (d[api_f] or "").strip())
        if "active" in d:
            p.activo = bool(d["active"])
        p.save()
        return Response(_pickup_point_item(p))

    def delete(self, request, pk):
        get_object_or_404(PuntoEntregaDestino, pk=pk).delete()
        return Response(status=204)


class ShipmentDetailView(_Base):
    def get(self, request, code):
        return Response(detail(get_object_or_404(_QS, codigo=code)))


class ShipmentAssignView(_Base):
    def post(self, request, code):
        envio = get_object_or_404(_QS, codigo=code)
        carrier = get_object_or_404(Transportista, pk=request.data.get("carrierId"))
        vehiculo = None
        if request.data.get("vehicleId"):
            vehiculo = get_object_or_404(TransportistaVehiculo, pk=request.data["vehicleId"])
        services.asignar_envio(envio, carrier, vehiculo=vehiculo, usuario=request.user)
        return Response(detail(get_object_or_404(_QS, codigo=code)))


class ShipmentDestinationCarriersView(_Base):
    """Afiliados activos en la ciudad destino de una encomienda interprovincial
    (por `Transportista.ubicacion_frecuente`) — candidatos para el reparto a
    domicilio en destino (Fase B)."""

    def get(self, request, code):
        envio = get_object_or_404(_QS, codigo=code)
        candidatos = Transportista.para_ubicacion(envio.destino_distrito)
        return Response({
            "carriers": [{"id": c.id, "name": c.nombre, "phone": c.telefono} for c in candidatos],
        })


class ShipmentAssignDestinationView(_Base):
    def post(self, request, code):
        envio = get_object_or_404(_QS, codigo=code)
        carrier = get_object_or_404(Transportista, pk=request.data.get("carrierId"))
        services.asignar_reparto_destino(envio, carrier, usuario=request.user)
        return Response(detail(get_object_or_404(_QS, codigo=code)))


class ShipmentEventsView(_Base):
    def post(self, request, code):
        envio = get_object_or_404(_QS, codigo=code)
        d = request.data
        services.registrar_evento(
            envio, d.get("state"), descripcion=(d.get("detail") or "").strip(),
            ubicacion=(d.get("location") or "").strip(),
            recibido_por=(d.get("receivedBy") or "").strip(),
            prueba_foto=(d.get("photo") or "").strip(),
            motivo_fallo=(d.get("failReason") or "").strip(),
            usuario=request.user,
        )
        return Response(detail(get_object_or_404(_QS, codigo=code)))


class ShipmentCancelView(_Base):
    def post(self, request, code):
        envio = get_object_or_404(_QS, codigo=code)
        services.cancelar_envio(envio, motivo=(request.data.get("reason") or "").strip(), usuario=request.user)
        return Response(detail(get_object_or_404(_QS, codigo=code)))


class ShipmentPodPhotoView(_Base):
    def get(self, request, code):
        from django.http import FileResponse, Http404
        envio = get_object_or_404(Envio, codigo=code)
        if not envio.prueba_foto:
            raise Http404("Sin foto de entrega.")
        resp = FileResponse(envio.prueba_foto.open("rb"))
        resp["Cache-Control"] = "private, max-age=86400"
        return resp


# --------------------------------------------------------------------------- #
#  Rutas de reparto (P2)
# --------------------------------------------------------------------------- #

def route_item(r):
    p = services.ruta_progreso(r)
    return {
        "code": r.codigo, "date": r.fecha.isoformat(), "state": r.estado,
        "carrierId": r.transportista_id, "carrierName": r.transportista.nombre,
        "total": p["total"], "done": p["done"], "delivered": p["delivered"],
        "startedAt": _d(r.iniciada_en), "closedAt": _d(r.cerrada_en),
    }


def route_detail(r):
    out = route_item(r)
    out["stops"] = [{
        "order": e.orden_ruta, "code": e.codigo, "state": e.estado,
        "stateLabel": e.get_estado_display(),
        "recipient": e.destinatario_nombre, "phone": e.destinatario_telefono,
        "district": e.destino_distrito, "address": e.destino_direccion, "reference": e.destino_referencia,
        "cod": e.es_contraentrega, "codAmount": _num(e.monto_contraentrega),
        "package": e.contenido,
    } for e in r.paradas.order_by("orden_ruta", "id")]
    return out


class RouteListView(_Base):
    def get(self, request):
        qs = RutaReparto.objects.select_related("transportista").prefetch_related("paradas")
        p = request.query_params
        if p.get("state"):
            qs = qs.filter(estado=p["state"])
        if p.get("date"):
            qs = qs.filter(fecha=p["date"])
        return Response({"results": [route_item(r) for r in qs[:100]]})

    def post(self, request):
        d = request.data
        carrier = get_object_or_404(Transportista, pk=d.get("carrierId"))
        try:
            fecha = datetime.strptime(d.get("date", "")[:10], "%Y-%m-%d").date()
        except ValueError:
            raise ValidationError({"date": "Fecha requerida (AAAA-MM-DD)."})
        vehiculo = None
        if d.get("vehicleId"):
            vehiculo = get_object_or_404(TransportistaVehiculo, pk=d["vehicleId"], transportista=carrier)
        envios = list(Envio.objects.filter(codigo__in=d.get("shipments") or []))
        ruta = services.crear_ruta(transportista=carrier, fecha=fecha, vehiculo=vehiculo,
                                   envios=envios, usuario=request.user)
        return Response(route_detail(ruta), status=201)


class RouteDetailView(_Base):
    def get(self, request, code):
        return Response(route_detail(get_object_or_404(RutaReparto, codigo=code)))


class RouteStopsView(_Base):
    def post(self, request, code):
        ruta = get_object_or_404(RutaReparto, codigo=code)
        d = request.data
        for c in d.get("add") or []:
            e = Envio.objects.filter(codigo=c).first()
            if e:
                services.agregar_a_ruta(ruta, e)
        for c in d.get("remove") or []:
            e = ruta.paradas.filter(codigo=c).first()
            if e:
                services.quitar_de_ruta(ruta, e)
        if d.get("order"):
            services.reordenar_ruta(ruta, orden_manual=d["order"])
        elif d.get("add"):
            services.reordenar_ruta(ruta)
        return Response(route_detail(get_object_or_404(RutaReparto, codigo=code)))


class RouteStartView(_Base):
    def post(self, request, code):
        services.iniciar_ruta(get_object_or_404(RutaReparto, codigo=code))
        return Response(route_detail(get_object_or_404(RutaReparto, codigo=code)))


class RouteCloseView(_Base):
    def post(self, request, code):
        services.cerrar_ruta(get_object_or_404(RutaReparto, codigo=code), usuario=request.user)
        return Response(route_detail(get_object_or_404(RutaReparto, codigo=code)))


# --------------------------------------------------------------------------- #
#  Portal del transportista — sus entregas
# --------------------------------------------------------------------------- #

class _CarrierBase(APIView):
    permission_classes = [IsCarrier]

    def get_exception_handler(self):
        return api_exception_handler

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.carrier = carrier_for(request.user)


def _stop_payload(e):
    return {
        "code": e.codigo, "state": e.estado, "order": e.orden_ruta,
        "pickup": {"district": e.origen_distrito, "address": e.origen_direccion,
                   "reference": e.origen_referencia, "contact": e.remitente_nombre, "phone": e.remitente_telefono},
        "dropoff": {"district": e.destino_distrito, "address": e.destino_direccion,
                    "reference": e.destino_referencia, "contact": e.destinatario_nombre, "phone": e.destinatario_telefono},
        "package": e.contenido or "",
        "weightKg": _num(e.peso_kg),
        "cod": e.es_contraentrega, "codAmount": _num(e.monto_contraentrega),
        "attempts": e.intentos_entrega,
    }


class CarrierDeliveriesView(_CarrierBase):
    def get(self, request):
        qs = (Envio.objects.filter(transportista=self.carrier, ruta__isnull=True)
              .filter(estado__in=list(Envio.ABIERTOS))
              .order_by("estado", "creado_en"))
        return Response({"results": [_stop_payload(e) for e in qs]})


class CarrierRouteView(_CarrierBase):
    """La ruta activa de hoy del motorizado (planificada o en curso)."""

    def _ruta(self):
        return (RutaReparto.objects
                .filter(transportista=self.carrier,
                        estado__in=[RutaReparto.ESTADO_PLANIFICADA, RutaReparto.ESTADO_EN_CURSO])
                .order_by("fecha").first())

    def get(self, request):
        r = self._ruta()
        if not r:
            return Response({"route": None})
        prog = services.ruta_progreso(r)
        return Response({"route": {
            "code": r.codigo, "date": r.fecha.isoformat(), "state": r.estado,
            "total": prog["total"], "done": prog["done"], "delivered": prog["delivered"],
            "stops": [_stop_payload(e) for e in r.paradas.order_by("orden_ruta", "id")],
        }})

    def post(self, request):
        r = self._ruta()
        if not r:
            raise ValidationError("No tenés una ruta para hoy.")
        services.iniciar_ruta(r)
        return Response({"ok": True})


class CarrierDeliveryEventView(_CarrierBase):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, code):
        envio = get_object_or_404(Envio, codigo=code, transportista=self.carrier)
        d = request.data
        allowed = {Envio.ESTADO_RECOGIDO, Envio.ESTADO_EN_RUTA, Envio.ESTADO_ENTREGADO, Envio.ESTADO_FALLIDO}
        if d.get("state") not in allowed:
            raise ValidationError({"state": "Estado no permitido desde el portal."})
        services.registrar_evento(
            envio, d["state"], descripcion=(d.get("detail") or "").strip(),
            recibido_por=(d.get("receivedBy") or "").strip(),
            prueba_foto=request.FILES.get("photo"),
            prueba_firma=(d.get("signature") or "").strip(),
            motivo_fallo=(d.get("failReason") or "").strip(),
            cod_cobrado=d.get("codCollected"),
            cod_medio=(d.get("codMethod") or "").strip(),
            cod_comprobante=request.FILES.get("codReceipt"),
            usuario=request.user,
        )
        return Response({"ok": True, "state": envio.estado})


# --------------------------------------------------------------------------- #
#  Contra-entrega (COD) — Finanzas
# --------------------------------------------------------------------------- #

_ROLES_COD = ("Administrador", "Gerencia", "Finanzas", "Despacho")


class _CodBase(APIView):
    permission_classes = [HasAnyRole(*_ROLES_COD)]

    def get_exception_handler(self):
        return api_exception_handler


class CodPendingView(_CodBase):
    def get(self, request):
        by = {}
        for e in services.cod_por_rendir():
            g = by.setdefault(e.transportista_id, {
                "carrierId": e.transportista_id, "carrierName": e.transportista.nombre,
                "count": 0, "total": 0.0, "shipments": [],
            })
            g["count"] += 1
            g["total"] += float(e.cod_cobrado)
            g["shipments"].append({"code": e.codigo, "amount": float(e.cod_cobrado), "method": e.cod_medio})
        return Response({"groups": list(by.values())})


class CodSettlementListView(_CodBase):
    def get(self, request):
        qs = RendicionCaja.objects.select_related("transportista")
        if request.query_params.get("state"):
            qs = qs.filter(estado=request.query_params["state"])
        return Response({"results": [{
            "code": r.codigo, "carrierName": r.transportista.nombre, "state": r.estado,
            "expected": _num(r.esperado), "handedOver": _num(r.entregado), "difference": _num(r.diferencia),
            "createdAt": _d(r.creado_en),
        } for r in qs[:100]]})

    def post(self, request):
        carrier = get_object_or_404(Transportista, pk=request.data.get("carrierId"))
        r = services.crear_rendicion(carrier, usuario=request.user)
        return Response({"code": r.codigo, "expected": _num(r.esperado)}, status=201)


class CodSettlementDetailView(_CodBase):
    def get(self, request, code):
        r = get_object_or_404(RendicionCaja.objects.select_related("transportista"), codigo=code)
        return Response({
            "code": r.codigo, "carrierName": r.transportista.nombre, "state": r.estado,
            "expected": _num(r.esperado), "handedOver": _num(r.entregado), "difference": _num(r.diferencia),
            "reference": r.referencia, "note": r.nota,
            "shipments": [{"code": e.codigo, "amount": _num(e.cod_cobrado), "method": e.cod_medio,
                           "recipient": e.destinatario_nombre} for e in r.envios.all()],
        })

    def post(self, request, code):
        r = get_object_or_404(RendicionCaja, codigo=code)
        d = request.data
        if d.get("amount") in (None, ""):
            raise ValidationError({"amount": "Ingresá cuánto entregó el motorizado."})
        services.conciliar_rendicion(
            r, entregado=d["amount"], usuario=request.user,
            referencia=(d.get("reference") or "").strip(), nota=(d.get("note") or "").strip(),
        )
        return Response({"ok": True})


class CodToRemitView(_CodBase):
    def get(self, request):
        by = {}
        for e in services.cod_por_remitir().select_related("transportista"):
            g = by.setdefault(e.remitente_nombre or "—", {
                "sender": e.remitente_nombre or "—", "phone": e.remitente_telefono,
                "count": 0, "total": 0.0, "shipments": [],
            })
            g["count"] += 1
            g["total"] += float(e.cod_a_remitir)
            g["shipments"].append({"code": e.codigo, "amount": float(e.cod_a_remitir)})
        return Response({"groups": list(by.values())})

    def post(self, request):
        codes = request.data.get("shipmentCodes") or []
        envios = list(Envio.objects.filter(codigo__in=codes))
        n = services.marcar_remitido(envios, referencia=(request.data.get("reference") or "").strip(),
                                     usuario=request.user)
        return Response({"remitted": n})


# --------------------------------------------------------------------------- #
#  Seguimiento público
# --------------------------------------------------------------------------- #

class PublicTrackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request, token):
        envio = get_object_or_404(Envio.objects.prefetch_related("eventos"), token=token)
        return Response(services.tracking_publico(envio))
