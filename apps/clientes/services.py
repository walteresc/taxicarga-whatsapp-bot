"""Consulta de clientes. Compartida entre panel viejo y API v2."""
from apps.api.filters import apply_active_filter, apply_ordering, apply_search
from apps.clientes.models import Cliente

_ORDERING = {
    "name": "nombre",
    "createdAt": "fecha_creacion",
    "lastInteraction": "ultima_interaccion",
}


def customers_queryset(params):
    qs = Cliente.objects.all()
    qs = apply_search(
        qs, params.get("search"),
        ("nombre", "display_name", "telefono", "documento", "correo", "razon_social"),
    )
    qs = apply_active_filter(qs, params.get("status"), field="is_active")
    qs = apply_ordering(qs, params.get("ordering"), _ORDERING, ("-fecha_creacion", "-id"))
    return qs
