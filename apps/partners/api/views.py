"""API pública de socios (P4) — para que una tienda mande sus pedidos.

Auth: `Authorization: Bearer <prefix>.<secreto>` (ApiKey). Todo bajo
`/api/partners/v1/`, fuera del namespace interno `/api/v2/`.

    GET  coverage                zonas + niveles de servicio
    POST quotes                  {originDistrict, destDistrict, weightKg, level}
    POST shipments                crea un envío (Idempotency-Key soportado)
    GET  shipments/<id>
    POST shipments/<id>/cancel
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.encomiendas import services
from apps.encomiendas.models import Envio, ZonaReparto
from apps.partners import services as partner_services

from .authentication import ApiKeyAuthentication, HasApiKey

_STATE_EN = {
    "registrado": "registered", "asignado": "assigned", "recogido": "picked_up",
    "en_ruta": "in_transit", "en_destino": "arrived_at_destination",
    "en_reparto_destino": "out_for_delivery_destination", "entregado": "delivered",
    "fallido": "failed", "devuelto": "returned", "cancelado": "cancelled",
}


def _num(v):
    return float(v) if v is not None else None


def shipment_payload(e):
    return {
        "id": e.codigo,
        "externalRef": e.external_ref or None,
        "state": _STATE_EN.get(e.estado, e.estado),
        "level": e.nivel,
        "price": _num(e.precio),
        "currency": "PEN",
        "trackingUrl": f"/seguimiento/{e.token}",
        "cod": e.es_contraentrega,
        "codAmount": _num(e.monto_contraentrega),
        "createdAt": e.creado_en.isoformat(),
        "deliveredAt": e.entregado_en.isoformat() if e.entregado_en else None,
    }


class _Base(APIView):
    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasApiKey]

    def get_exception_handler(self):
        return api_exception_handler

    @property
    def socio(self):
        return self.request.auth.socio


class CoverageView(_Base):
    def get(self, request):
        return Response({
            "zones": [{"name": z.nombre, "districts": z.distritos} for z in ZonaReparto.objects.filter(activo=True)],
            "levels": [{"value": v, "label": lbl} for v, lbl in Envio.NIVELES],
        })


class QuoteView(_Base):
    def post(self, request):
        d = request.data
        try:
            r = services.cotizar(
                origen_distrito=d.get("originDistrict", ""), destino_distrito=d.get("destDistrict", ""),
                nivel=d.get("level") or Envio.NIVEL_EXPRESS, peso_kg=d.get("weightKg") or 1,
            )
        except DjangoValidationError as e:
            raise ValidationError(e.message_dict if hasattr(e, "message_dict") else str(e))
        return Response({
            "price": r["price"], "currency": "PEN", "level": r["level"], "etaHours": r["etaHours"],
        })


_SHIPMENT_FIELDS = {
    "senderName": "remitente_nombre", "senderPhone": "remitente_telefono",
    "originDistrict": "origen_distrito", "originAddress": "origen_direccion", "originReference": "origen_referencia",
    "recipientName": "destinatario_nombre", "recipientPhone": "destinatario_telefono",
    "destDistrict": "destino_distrito", "destAddress": "destino_direccion", "destReference": "destino_referencia",
    "destPickupPoint": "punto_entrega_destino",
    "originLat": "origen_lat", "originLng": "origen_lng", "destLat": "destino_lat", "destLng": "destino_lng",
    "content": "contenido", "weightKg": "peso_kg", "lengthCm": "largo_cm", "widthCm": "ancho_cm", "heightCm": "alto_cm",
    "declaredValue": "valor_declarado", "cod": "es_contraentrega", "codAmount": "monto_contraentrega",
    "level": "nivel", "externalRef": "external_ref",
}
_REQUIRED = ("senderName", "originDistrict", "originAddress", "recipientName", "destDistrict", "destAddress")


class ShipmentListView(_Base):
    def post(self, request):
        idem_key = request.META.get("HTTP_IDEMPOTENCY_KEY", "")

        def _crear():
            for f in _REQUIRED:
                if not str(request.data.get(f, "")).strip():
                    raise ValidationError({f: "Requerido."})
            data = {model_f: request.data[api_f] for api_f, model_f in _SHIPMENT_FIELDS.items() if api_f in request.data}
            data["socio"] = self.socio
            try:
                envio = services.crear_envio(data, usuario=None)
            except DjangoValidationError as e:
                raise ValidationError(e.message_dict if hasattr(e, "message_dict") else str(e))
            return 201, shipment_payload(envio)

        status, body, replayed = partner_services.con_idempotencia(self.socio, idem_key, "POST /shipments", _crear)
        resp = Response(body, status=status)
        if replayed:
            resp["Idempotent-Replayed"] = "true"
        return resp


class ShipmentDetailView(_Base):
    def get(self, request, code):
        envio = get_object_or_404(Envio, codigo=code, socio=self.socio)
        return Response(shipment_payload(envio))


class ShipmentCancelView(_Base):
    def post(self, request, code):
        envio = get_object_or_404(Envio, codigo=code, socio=self.socio)
        try:
            services.cancelar_envio(envio, motivo=(request.data.get("reason") or "Cancelado por el socio."))
        except DjangoValidationError as e:
            raise ValidationError(str(e))
        return Response(shipment_payload(envio))
