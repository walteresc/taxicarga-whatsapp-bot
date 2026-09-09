"""API v2: transportistas afiliados y sus vehículos.

    GET/POST         /api/v2/carriers/            /api/v2/carrier-vehicles/
    GET/PATCH/DELETE .../{id}/
    POST             /api/v2/carriers/{id}/toggle-active/
    carrier-vehicles acepta ?carrierId= para filtrar.
"""
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.api.filters import apply_active_filter, apply_ordering, apply_search
from apps.api.permissions import HasAnyRole
from apps.api.views import V2ModelViewSet
from apps.tercerizacion.models import (
    Transportista, TransportistaConductor, TransportistaVehiculo,
)

from .serializers import CarrierDriverSerializer, CarrierSerializer, CarrierVehicleSerializer

_ROLES = ("Administrador", "Supervisor", "Asesor de Ventas")

_CARRIER_ORDER = {"name": "nombre", "createdAt": "creado_en"}
_VEHICLE_ORDER = {"plate": "placa", "createdAt": "creado_en", "carrier": "transportista__nombre"}


class CarrierViewSet(V2ModelViewSet):
    serializer_class = CarrierSerializer
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        from django.db.models import Count, Q

        p = self.request.query_params
        qs = Transportista.objects.prefetch_related("vehiculos").annotate(
            useCount=Count(
                "programaciones",
                filter=~Q(programaciones__estado_operativo="cancelado"),
                distinct=True,
            ),
        )
        qs = apply_search(qs, p.get("search"), ("nombre", "documento", "telefono", "email"))
        qs = apply_active_filter(qs, p.get("status"))
        if p.get("ordering") == "frequency":
            return qs.order_by("-useCount", "nombre", "id")
        return apply_ordering(qs, p.get("ordering"), _CARRIER_ORDER, ("nombre", "id"))

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        obj = self.get_object()
        obj.activo = not obj.activo
        obj.save(update_fields=["activo"])
        return Response(self.get_serializer(obj).data)


class CarrierVehicleViewSet(V2ModelViewSet):
    serializer_class = CarrierVehicleSerializer
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        p = self.request.query_params
        qs = TransportistaVehiculo.objects.select_related(
            "transportista", "tipo_vehiculo", "tipo_carroceria", "categoria",
        )
        if p.get("carrierId"):
            qs = qs.filter(transportista_id=p["carrierId"])
        qs = apply_search(qs, p.get("search"), ("placa", "marca", "modelo", "transportista__nombre"))
        qs = apply_active_filter(qs, p.get("status"))
        return apply_ordering(qs, p.get("ordering"), _VEHICLE_ORDER, ("placa", "id"))

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        obj = self.get_object()
        obj.activo = not obj.activo
        obj.save()
        return Response(self.get_serializer(obj).data)


_DRIVER_ORDER = {"name": "nombre", "documentId": "dni", "carrier": "transportista__nombre"}


class CarrierDriverViewSet(V2ModelViewSet):
    serializer_class = CarrierDriverSerializer
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        p = self.request.query_params
        qs = TransportistaConductor.objects.select_related("transportista")
        if p.get("carrierId"):
            qs = qs.filter(transportista_id=p["carrierId"])
        qs = apply_search(qs, p.get("search"), ("nombre", "dni", "telefono", "transportista__nombre"))
        qs = apply_active_filter(qs, p.get("status"))
        return apply_ordering(qs, p.get("ordering"), _DRIVER_ORDER, ("nombre", "id"))

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        obj = self.get_object()
        obj.activo = not obj.activo
        obj.save(update_fields=["activo"])
        return Response(self.get_serializer(obj).data)
