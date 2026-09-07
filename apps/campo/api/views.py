"""Viewsets de la API v2 para Personal. Finos: permisos + serializer + servicio.

Endpoints (montados en /api/v2/):
    GET/POST         /drivers/            /assistants/
    GET/PATCH/DELETE /drivers/{id}/       /assistants/{id}/
    POST             /drivers/{id}/toggle-active/   (atajo de activar/desactivar)

Lista: ?search=&status=active|inactive&ordering=name|-licenseExpiresOn&page=&pageSize=
Respuesta y errores: formato estándar de apps.api (ver docs/PATRON-API-VUE.md).
"""
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.api.permissions import HasAnyRole
from apps.api.views import V2ModelViewSet
from apps.campo.services import assistants_queryset, drivers_queryset

from .serializers import AssistantSerializer, DriverSerializer

_ROLES = ("Administrador", "Supervisor", "Asesor de Ventas")


class _PersonnelViewSet(V2ModelViewSet):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        return self._queryset_fn(self.request.query_params)

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        obj = self.get_object()
        obj.activo = not obj.activo
        obj.save(update_fields=["activo"])
        return Response(self.get_serializer(obj).data)


class DriverViewSet(_PersonnelViewSet):
    serializer_class = DriverSerializer
    _queryset_fn = staticmethod(drivers_queryset)


class AssistantViewSet(_PersonnelViewSet):
    serializer_class = AssistantSerializer
    _queryset_fn = staticmethod(assistants_queryset)
