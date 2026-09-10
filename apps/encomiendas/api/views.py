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
from apps.encomiendas.models import Envio, RutaReparto, TarifaZona, ZonaReparto
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
                   "district": e.origen_distrito, "address": e.origen_direccion, "reference": e.origen_referencia},
        "recipientFull": {"name": e.destinatario_nombre, "phone": e.destinatario_telefono,
                          "district": e.destino_distrito, "address": e.destino_direccion, "reference": e.destino_referencia},
        "package": {"content": e.contenido, "weightKg": _num(e.peso_kg),
                    "lengthCm": e.largo_cm, "widthCm": e.ancho_cm, "heightCm": e.alto_cm,
                    "declaredValue": _num(e.valor_declarado)},
        "carrierVehicleId": e.transportista_vehiculo_id,
        "routeCode": e.ruta.codigo if e.ruta_id else None,
        "receivedBy": e.recibido_por or None,
        "podPhoto": f"/api/v2/shipments/{e.codigo}/pod-photo" if e.prueba_foto else None,
        "hasSignature": bool(e.prueba_firma),
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
    "content": "contenido", "weightKg": "peso_kg", "lengthCm": "largo_cm", "widthCm": "ancho_cm", "heightCm": "alto_cm",
    "declaredValue": "valor_declarado", "cod": "es_contraentrega", "codAmount": "monto_contraentrega",
    "notes": "notas", "price": "precio",
}


class _Base(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler


_QS = Envio.objects.select_related("transportista").prefetch_related("eventos")


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
            "levels": [{"value": v, "label": lbl} for v, lbl in TarifaZona.NIVELES],
        })


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
            usuario=request.user,
        )
        return Response({"ok": True, "state": envio.estado})


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
