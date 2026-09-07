"""Lógica de consulta del módulo Personal (conductores / ayudantes).

Separada de las vistas para que la comparta el panel viejo (Django) y la API v2
(Vue). Solo lectura/filtrado; las escrituras van por el serializer del API o por
los forms del panel viejo.
"""
from apps.api.filters import apply_active_filter, apply_ordering, apply_search
from apps.campo.models import Ayudante, Conductor

_DRIVER_ORDERING = {
    "name": "nombre", "documentId": "dni", "licenseExpiresOn": "fecha_vencimiento_licencia",
    "active": "activo",
}
_ASSISTANT_ORDERING = {"name": "nombre", "documentId": "dni", "active": "activo"}


def drivers_queryset(params):
    qs = Conductor.objects.select_related("usuario").all()
    qs = apply_search(qs, params.get("search"), ("nombre", "dni", "telefono", "numero_licencia"))
    qs = apply_active_filter(qs, params.get("status"))
    qs = apply_ordering(qs, params.get("ordering"), _DRIVER_ORDERING, ("nombre", "id"))
    return qs


def assistants_queryset(params):
    qs = Ayudante.objects.select_related("usuario").all()
    qs = apply_search(qs, params.get("search"), ("nombre", "dni", "telefono"))
    qs = apply_active_filter(qs, params.get("status"))
    qs = apply_ordering(qs, params.get("ordering"), _ASSISTANT_ORDERING, ("nombre", "id"))
    return qs
