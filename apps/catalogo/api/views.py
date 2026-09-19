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


class PublicVehiclePickerView(APIView):
    """Datos del catálogo real de vehículos para el selector de vehículo del
    cotizador (invitado/portal cliente) — carrocería + unidades disponibles
    con su capacidad. Público y de solo lectura."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        # Qué tipos de vehículo aparecen acá es editable desde Configuración →
        # Catálogo → Tipos de Vehículos (columna "Visible en cotizador
        # público") — antes era una lista fija en el código que nadie podía
        # tocar sin desplegar (_VEHICLE_CODES_PUBLICOS, ya retirada).
        tipos = list(
            TipoVehiculo.objects.filter(habilitado=True, visible_cotizador_publico=True)
            .prefetch_related("categorias__compatibilidades__tipo_carroceria")
        )
        # Todas las categorías de todos los tipos habilitados, en UNA sola
        # lista ordenada globalmente por su propio "Orden" (Configuración →
        # Catálogo → Categorización) — antes se agrupaba primero por tipo de
        # vehículo y recién adentro por orden, así que una categoría con
        # orden más bajo (p. ej. Semitrailer 20 ton) podía salir después de
        # otra con orden más alto pero del mismo tipo agrupado antes (p. ej.
        # Camión Grúa 5 ton), aunque el admin haya puesto un orden global
        # pensado para intercalar tipos de vehículo.
        pares = sorted(
            ((cat, tv) for tv in tipos for cat in tv.categorias.all() if cat.habilitado),
            key=lambda par: (par[0].orden, par[0].id),
        )
        body_codes_seen = {}
        units = []
        for cat, tv in pares:
            # La carrocería compatible es por CATEGORÍA puntual (tonelaje),
            # no por tipo de vehículo genérico — un "Camión 2 ton" no
            # admite lo mismo que un "Camión 15 ton".
            compat_rows = list(cat.compatibilidades.all())
            # Las combinaciones con "nombre_cliente" (p. ej. Semitrailer 20
            # ton + carrocería Cigüeña) NO se listan como una carrocería más
            # dentro de esta unidad — se muestran aparte, como su propia
            # "unidad" con nombre propio (ver más abajo). Así el cliente ve
            # "Cigüeña" en vez de "Semitrailer 20 ton" con una carrocería
            # más entre varias.
            body_types = sorted(
                (c.tipo_carroceria for c in compat_rows if c.tipo_carroceria.habilitado and not c.nombre_cliente),
                key=lambda bt: (bt.orden, bt.nombre),
            )
            for bt in body_types:
                body_codes_seen[bt.codigo] = bt
            min_ton = float(cat.min_ton) if cat.min_ton is not None else None
            max_ton = float(cat.max_ton) if cat.max_ton is not None else None
            units.append({
                "code": str(cat.id),
                "name": cat.nombre,
                "vehicleType": tv.codigo,
                # Categoría de peso (Menores/Livianos/Medianos/Pesados/Especiales) es el
                # filtro principal del selector — la carrocería queda como dato
                # informativo, no como filtro obligatorio (la decide el transportista
                # al aceptar el servicio, no el cliente al pedirlo).
                "weightCategory": cat.categoria,
                "minTon": min_ton,
                "maxTon": max_ton,
                "bodyTypes": [bt.codigo for bt in body_types],
            })
            # Unidades "virtuales": misma categoría real (mismo vehículo y
            # tonelaje), pero mostradas con nombre propio y carrocería fija
            # — al confirmarlas, el cliente pide exactamente esa categoría +
            # esa carrocería, aunque el transportista dio de alta su
            # vehículo real normalmente (categoría real + carrocería real,
            # sin nada especial de su lado).
            for c in sorted(compat_rows, key=lambda c: c.tipo_carroceria.orden):
                if not c.nombre_cliente or not c.tipo_carroceria.habilitado:
                    continue
                body_codes_seen[c.tipo_carroceria.codigo] = c.tipo_carroceria
                units.append({
                    "code": f"{cat.id}:{c.tipo_carroceria_id}",
                    "name": c.nombre_cliente,
                    "vehicleType": tv.codigo,
                    # Categoría de peso propia si se configuró (p. ej. una
                    # "Camión 5 ton" normal es "Livianos", pero la variante
                    # con grúa de esa misma categoría real se quiere mostrar
                    # al cliente en "Especiales") — si no, hereda la de la
                    # categoría real de base, como antes.
                    "weightCategory": c.categoria_cliente or cat.categoria,
                    "minTon": min_ton,
                    "maxTon": max_ton,
                    "bodyTypes": [c.tipo_carroceria.codigo],
                    "fixedBodyType": c.tipo_carroceria.codigo,
                })
        # En "Todas" (sin filtrar por categoría de peso) las unidades quedaban
        # intercaladas por su "Orden" global sin agrupar — un Camión Grúa 5
        # ton (Especiales) podía salir en medio de los Camión 6/7/8 ton
        # (Livianos/Medianos), mezclado con los chips de arriba (Livianos,
        # Medianos, Pesados, Especiales). Se reordena una sola vez, de forma
        # ESTABLE, para que agrupe por esa misma categoría de peso y en ese
        # mismo orden — dentro de cada grupo se conserva el orden ya armado
        # arriba (el "Orden" configurado, intercalando tipos de vehículo).
        peso_rank = {code: i for i, (code, _) in enumerate(CategoriaVehiculo.CATEGORIAS)}
        units.sort(key=lambda u: peso_rank.get(u["weightCategory"], 99))

        body_types = [
            {"code": bt.codigo, "name": bt.nombre, "icon": bt.icono or "ri-truck-line"}
            for bt in sorted(body_codes_seen.values(), key=lambda b: (b.orden, b.nombre))
        ]
        # Solo las categorías de peso que de verdad quedaron con unidades acá —
        # no toda CategoriaVehiculo.CATEGORIAS. Por ejemplo "Menores" existe
        # como categoría (Moto, Auto), pero esos tipos de vehículo no están
        # marcados "Visible en cotizador público" — se autoactualiza si algún
        # día se habilita ahí Moto/Auto, o se le asigna esa categoría a una
        # fila de Camión/Camioneta.
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
