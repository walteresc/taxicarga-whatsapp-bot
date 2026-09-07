"""Viewsets de la API v2 para Flota. Aplican el patrón de Personal.

    GET/POST         /api/v2/vehicles/            /api/v2/maintenance/
    GET/PATCH/DELETE /api/v2/vehicles/{id}/       /api/v2/maintenance/{id}/
    POST             /api/v2/vehicles/{id}/toggle-active/
    GET              /api/v2/vehicles/alerts/     (avisos de vencimientos)

maintenance acepta ?vehicleId= para filtrar por vehículo.
"""
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.api.permissions import HasAnyRole
from apps.api.views import V2ModelViewSet
from apps.flota.services import (
    maintenance_queryset, vehicle_alerts, vehicles_queryset,
)

from .serializers import MaintenanceSerializer, VehicleSerializer

_ROLES = ("Administrador", "Supervisor", "Asesor de Ventas")


class VehicleViewSet(V2ModelViewSet):
    serializer_class = VehicleSerializer
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        return vehicles_queryset(self.request.query_params)

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        obj = self.get_object()
        obj.activo = not obj.activo
        obj.save(update_fields=["activo"])
        return Response(self.get_serializer(obj).data)

    @action(detail=False, methods=["get"])
    def alerts(self, request):
        return Response(vehicle_alerts())


class MaintenanceViewSet(V2ModelViewSet):
    serializer_class = MaintenanceSerializer
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        return maintenance_queryset(self.request.query_params)
