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


from rest_framework.views import APIView  # noqa: E402

from apps.api.exceptions import api_exception_handler  # noqa: E402


class PersonnelDirectoryView(APIView):
    """Directorio unificado de personal propio: conductores + ayudantes + asesores.
    Solo lectura. Filtros: ?type=conductor|ayudante|asesor  ?status=active|inactive
    ?search=  ?page=&pageSize=. El alta/edición sigue por cada recurso específico."""
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        from django.contrib.auth import get_user_model

        from apps.api.pagination import StandardPagination
        from apps.campo.models import Ayudante, Conductor

        tipo = (request.query_params.get("type") or "").strip().lower()
        status = (request.query_params.get("status") or "").strip().lower()
        term = (request.query_params.get("search") or "").strip().lower()

        rows = []
        if tipo in ("", "conductor"):
            for c in Conductor.objects.all():
                rows.append({
                    "id": f"c{c.id}", "sourceId": c.id, "type": "conductor",
                    "name": c.nombre, "documentId": c.dni, "phone": c.telefono,
                    "detail": (f"Lic. {c.numero_licencia}" if c.numero_licencia else ""),
                    "active": c.activo,
                })
        if tipo in ("", "ayudante"):
            for a in Ayudante.objects.all():
                rows.append({
                    "id": f"a{a.id}", "sourceId": a.id, "type": "ayudante",
                    "name": a.nombre, "documentId": a.dni, "phone": a.telefono,
                    "detail": "", "active": a.activo,
                })
        if tipo in ("", "asesor"):
            User = get_user_model()
            for u in User.objects.filter(groups__name="Asesor de Ventas").distinct():
                rows.append({
                    "id": f"u{u.id}", "sourceId": u.id, "type": "asesor",
                    "name": (u.get_full_name() or u.username), "documentId": "",
                    "phone": "", "detail": u.email, "active": u.is_active,
                })

        if status == "active":
            rows = [r for r in rows if r["active"]]
        elif status == "inactive":
            rows = [r for r in rows if not r["active"]]
        if term:
            rows = [r for r in rows if term in (r["name"] + r["documentId"] + r["phone"]).lower()]

        rows.sort(key=lambda r: r["name"].lower())

        paginator = StandardPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(page)
