"""Viewsets de la API v2 del catálogo de vehículos.

    GET/POST         /api/v2/vehicle-types/       body-types/      vehicle-categories/
    GET/PATCH/DELETE .../{id}/
    POST             .../{id}/toggle-active/
    GET              /api/v2/catalog/vehicle-picker  (público, ver PublicVehiclePickerView)
"""
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import HasAnyRole
from apps.api.views import V2ModelViewSet
from apps.catalogo import services
from apps.catalogo.models import CategoriaVehiculo, CompatibilidadCarroceria, TipoVehiculo

from .serializers import BodyTypeSerializer, VehicleCategorySerializer, VehicleTypeSerializer

_ROLES = ("Administrador", "Supervisor")

# Tipos de vehículo relevantes para cotizar Carga de cara al cliente — a
# propósito se dejan afuera Moto/Auto/Minivan (no aplican a "carga") y
# Semitrailer/Camión Remolque (carga muy pesada/especial, fuera del alcance
# de este cotizador rápido).
_VEHICLE_CODES_PUBLICOS = ["camioneta", "camion"]


class PublicVehiclePickerView(APIView):
    """Datos del catálogo real de vehículos para el selector de vehículo del
    cotizador (invitado/portal cliente) — carrocería + unidades disponibles
    con su capacidad. Público y de solo lectura."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        tipos = list(
            TipoVehiculo.objects.filter(habilitado=True, codigo__in=_VEHICLE_CODES_PUBLICOS)
            .prefetch_related("categorias", "compatibilidades__tipo_carroceria")
            .order_by("orden", "nombre")
        )
        body_codes_seen = {}
        units = []
        for tv in tipos:
            body_types = [
                c.tipo_carroceria for c in tv.compatibilidades.all() if c.tipo_carroceria.habilitado
            ]
            for bt in body_types:
                body_codes_seen[bt.codigo] = bt
            body_codes = [bt.codigo for bt in body_types]
            for cat in tv.categorias.filter(habilitado=True).order_by("orden", "id"):
                units.append({
                    "code": str(cat.id),
                    "name": cat.nombre,
                    "vehicleType": tv.codigo,
                    # Categoría de peso (Menores/Livianos/Medianos/Pesados/Especiales) es el
                    # filtro principal del selector — la carrocería queda como dato
                    # informativo, no como filtro obligatorio (la decide el transportista
                    # al aceptar el servicio, no el cliente al pedirlo).
                    "weightCategory": cat.categoria,
                    "minTon": float(cat.min_ton) if cat.min_ton is not None else None,
                    "maxTon": float(cat.max_ton) if cat.max_ton is not None else None,
                    "bodyTypes": body_codes,
                })
        body_types = [
            {"code": bt.codigo, "name": bt.nombre, "icon": bt.icono or "ri-truck-line"}
            for bt in sorted(body_codes_seen.values(), key=lambda b: (b.orden, b.nombre))
        ]
        # Solo las categorías de peso que de verdad quedaron con unidades acá —
        # no toda CategoriaVehiculo.CATEGORIAS. Por ejemplo "Menores" existe
        # como categoría (Moto, Auto), pero esos tipos de vehículo están afuera
        # de _VEHICLE_CODES_PUBLICOS a propósito, así que nunca debería
        # aparecer como filtro en este selector — se autoactualiza si algún
        # día se le asigna una fila de Camión/Camioneta.
        codes_con_unidades = {u["weightCategory"] for u in units}
        weight_categories = [
            {"code": code, "name": name} for code, name in CategoriaVehiculo.CATEGORIAS if code in codes_con_unidades
        ]
        return Response({"bodyTypes": body_types, "weightCategories": weight_categories, "units": units})


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
