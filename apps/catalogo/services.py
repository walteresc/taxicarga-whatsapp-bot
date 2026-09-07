"""Querysets con búsqueda/orden/estado para la API v2 del catálogo."""
from apps.api.filters import apply_active_filter, apply_ordering, apply_search

from .models import CategoriaVehiculo, TipoCarroceria, TipoVehiculo

_VT_ORDER = {"name": "nombre", "code": "codigo", "order": "orden", "enabled": "habilitado"}
_BT_ORDER = _VT_ORDER
_CAT_ORDER = {
    "name": "nombre", "order": "orden", "category": "categoria",
    "minTons": "min_ton", "maxTons": "max_ton", "vehicleType": "tipo_vehiculo__nombre",
}


def vehicle_types_queryset(params):
    qs = TipoVehiculo.objects.prefetch_related("compatibilidades")
    qs = apply_search(qs, params.get("search"), ("nombre", "codigo"))
    qs = apply_active_filter(qs, params.get("status"), field="habilitado")
    return apply_ordering(qs, params.get("ordering"), _VT_ORDER, ("orden", "nombre"))


def body_types_queryset(params):
    qs = TipoCarroceria.objects.all()
    qs = apply_search(qs, params.get("search"), ("nombre", "codigo"))
    qs = apply_active_filter(qs, params.get("status"), field="habilitado")
    return apply_ordering(qs, params.get("ordering"), _BT_ORDER, ("orden", "nombre"))


def vehicle_categories_queryset(params):
    qs = CategoriaVehiculo.objects.select_related("tipo_vehiculo")
    qs = apply_search(qs, params.get("search"), ("nombre", "tipo_vehiculo__nombre"))
    qs = apply_active_filter(qs, params.get("status"), field="habilitado")
    vt = params.get("vehicleTypeId")
    if vt:
        qs = qs.filter(tipo_vehiculo_id=vt)
    return apply_ordering(qs, params.get("ordering"), _CAT_ORDER, ("orden", "id"))
