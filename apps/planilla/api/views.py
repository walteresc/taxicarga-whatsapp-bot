"""Viewsets de la API v2 de Planilla."""
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.api.permissions import HasAnyRole
from apps.api.views import V2ModelViewSet
from apps.planilla.services import configs_queryset

from .serializers import PayrollConfigSerializer

_ROLES = ("Administrador", "Supervisor", "Asesor de Ventas")


class PayrollConfigViewSet(V2ModelViewSet):
    serializer_class = PayrollConfigSerializer
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        return configs_queryset(self.request.query_params)

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        obj = self.get_object()
        obj.activo = not obj.activo
        obj.save(update_fields=["activo"])
        return Response(self.get_serializer(obj).data)
