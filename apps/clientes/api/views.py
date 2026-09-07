"""Viewset de la API v2 para Clientes.

Sin DELETE a propósito: `Cliente` tiene CASCADE hacia `ConversacionWhatsApp`
(bandeja), `Lead` y `EvidenciaWhatsapp`. Borrar un cliente borraría su
conversación de la bandeja. En su lugar, `toggle-active` (soft-delete con
`is_active`, el mismo campo que usa el sistema para duplicados/merges).

    GET/POST         /api/v2/customers/
    GET/PATCH        /api/v2/customers/{id}/
    POST             /api/v2/customers/{id}/toggle-active/
"""
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.api.permissions import HasAnyRole
from apps.api.views import V2ModelViewSet
from apps.clientes.services import customers_queryset

from .serializers import CustomerSerializer

_ROLES = ("Administrador", "Supervisor", "Asesor de Ventas")


class CustomerViewSet(V2ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [HasAnyRole(*_ROLES)]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return customers_queryset(self.request.query_params)

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = not obj.is_active
        obj.save(update_fields=["is_active"])
        return Response(self.get_serializer(obj).data)
