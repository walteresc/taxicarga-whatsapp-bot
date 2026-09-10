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
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.pagination import StandardPagination
from apps.api.permissions import HasAnyRole, IsCarrier, carrier_for
from apps.encomiendas import services
from apps.encomiendas.models import Envio, TarifaZona, ZonaReparto
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
        "receivedBy": e.recibido_por or None,
        "failReason": e.motivo_fallo or None,
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


class CarrierDeliveriesView(_CarrierBase):
    def get(self, request):
        qs = (Envio.objects.filter(transportista=self.carrier)
              .exclude(estado__in=[Envio.ESTADO_CANCELADO, Envio.ESTADO_DEVUELTO])
              .order_by("estado", "creado_en"))
        return Response({"results": [{
            "code": e.codigo,
            "state": e.estado,
            "level": e.nivel,
            "pickup": {"district": e.origen_distrito, "address": e.origen_direccion,
                       "reference": e.origen_referencia, "contact": e.remitente_nombre, "phone": e.remitente_telefono},
            "dropoff": {"district": e.destino_distrito, "address": e.destino_direccion,
                        "reference": e.destino_referencia, "contact": e.destinatario_nombre, "phone": e.destinatario_telefono},
            "package": e.contenido,
            "cod": e.es_contraentrega,
            "codAmount": _num(e.monto_contraentrega),
        } for e in qs]})


class CarrierDeliveryEventView(_CarrierBase):
    def post(self, request, code):
        envio = get_object_or_404(Envio, codigo=code, transportista=self.carrier)
        d = request.data
        allowed = {Envio.ESTADO_RECOGIDO, Envio.ESTADO_EN_RUTA, Envio.ESTADO_ENTREGADO, Envio.ESTADO_FALLIDO}
        if d.get("state") not in allowed:
            raise ValidationError({"state": "Estado no permitido desde el portal."})
        services.registrar_evento(
            envio, d["state"], descripcion=(d.get("detail") or "").strip(),
            recibido_por=(d.get("receivedBy") or "").strip(),
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
