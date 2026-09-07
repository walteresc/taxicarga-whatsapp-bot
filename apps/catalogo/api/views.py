"""Viewsets de la API v2 del catálogo de vehículos.

    GET/POST         /api/v2/vehicle-types/       body-types/      vehicle-categories/
    GET/PATCH/DELETE .../{id}/
    POST             .../{id}/toggle-active/
"""
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.api.permissions import HasAnyRole
from apps.api.views import V2ModelViewSet
from apps.catalogo import services

from .serializers import BodyTypeSerializer, VehicleCategorySerializer, VehicleTypeSerializer

_ROLES = ("Administrador", "Supervisor")


class _ToggleMixin:
    _toggle_field = "habilitado"

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        obj = self.get_object()
        setattr(obj, self._toggle_field, not getattr(obj, self._toggle_field))
        obj.save(update_fields=[self._toggle_field])
        return Response(self.get_serializer(obj).data)


class VehicleTypeViewSet(_ToggleMixin, V2ModelViewSet):
    serializer_class = VehicleTypeSerializer
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        return services.vehicle_types_queryset(self.request.query_params)


class BodyTypeViewSet(_ToggleMixin, V2ModelViewSet):
    serializer_class = BodyTypeSerializer
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        return services.body_types_queryset(self.request.query_params)


class VehicleCategoryViewSet(_ToggleMixin, V2ModelViewSet):
    serializer_class = VehicleCategorySerializer
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        return services.vehicle_categories_queryset(self.request.query_params)
