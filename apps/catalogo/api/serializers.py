"""Serializers de la API v2 del catálogo. Claves inglesas vía `source=`."""
from rest_framework import serializers

from apps.catalogo.models import (
    CategoriaVehiculo, CompatibilidadCarroceria, TipoCarroceria, TipoVehiculo,
)


class VehicleTypeSerializer(serializers.ModelSerializer):
    code = serializers.SlugField(source="codigo", max_length=40)
    name = serializers.CharField(source="nombre", max_length=80)
    icon = serializers.CharField(source="icono", max_length=60, required=False, allow_blank=True, default="")
    enabled = serializers.BooleanField(source="habilitado", required=False, default=True)
    order = serializers.IntegerField(source="orden", required=False, default=0)
    visibleInPublicQuoter = serializers.BooleanField(source="visible_cotizador_publico", required=False, default=False)

    class Meta:
        model = TipoVehiculo
        fields = (
            "id", "code", "name", "icon", "enabled", "order", "visibleInPublicQuoter",
        )

    def validate_code(self, value):
        qs = TipoVehiculo.objects.filter(codigo=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un tipo con este código.")
        return value


class BodyTypeSerializer(serializers.ModelSerializer):
    code = serializers.SlugField(source="codigo", max_length=60)
    name = serializers.CharField(source="nombre", max_length=80)
    icon = serializers.CharField(source="icono", max_length=60, required=False, allow_blank=True, default="")
    enabled = serializers.BooleanField(source="habilitado", required=False, default=True)
    order = serializers.IntegerField(source="orden", required=False, default=0)

    class Meta:
        model = TipoCarroceria
        fields = ("id", "code", "name", "icon", "enabled", "order")

    def validate_code(self, value):
        qs = TipoCarroceria.objects.filter(codigo=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe una carrocería con este código.")
        return value


class VehicleCategorySerializer(serializers.ModelSerializer):
    vehicleTypeId = serializers.PrimaryKeyRelatedField(
        source="tipo_vehiculo", queryset=TipoVehiculo.objects.all(),
    )
    vehicleTypeName = serializers.CharField(source="tipo_vehiculo.nombre", read_only=True)
    name = serializers.CharField(source="nombre", max_length=80)
    category = serializers.ChoiceField(source="categoria", choices=CategoriaVehiculo.CATEGORIAS)
    minTons = serializers.DecimalField(
        source="min_ton", max_digits=6, decimal_places=2, required=False, allow_null=True, default=None,
    )
    maxTons = serializers.DecimalField(
        source="max_ton", max_digits=6, decimal_places=2, required=False, allow_null=True, default=None,
    )
    order = serializers.IntegerField(source="orden", required=False, default=0)
    enabled = serializers.BooleanField(source="habilitado", required=False, default=True)
    # Compatibilidad de carrocería: por CATEGORÍA puntual (tonelaje), no por
    # tipo de vehículo genérico — un "Camión 2 ton" y un "Camión 15 ton" no
    # tienen por qué admitir las mismas carrocerías.
    compatibleBodyTypeIds = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=TipoCarroceria.objects.all(), source="_compat_write",
    )
    compatibleBodyTypes = serializers.SerializerMethodField()
    # Nombre propio opcional por combinación categoría+carrocería (ver
    # CompatibilidadCarroceria.nombre_cliente) — {"<tipoCarroceriaId>": "Nombre"}.
    # Solo hace falta mandar las que se quieran fijar/cambiar/borrar; el resto
    # queda como estaba.
    bodyTypeDisplayNames = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=80, required=False),
        required=False, source="_display_names_write",
    )

    class Meta:
        model = CategoriaVehiculo
        fields = (
            "id", "vehicleTypeId", "vehicleTypeName", "name", "category",
            "minTons", "maxTons", "order", "enabled",
            "compatibleBodyTypeIds", "compatibleBodyTypes", "bodyTypeDisplayNames",
        )

    def get_compatibleBodyTypes(self, obj):
        compat = sorted(
            obj.compatibilidades.select_related("tipo_carroceria").all(),
            key=lambda c: (c.tipo_carroceria.orden, c.tipo_carroceria.nombre),
        )
        return [
            {"id": c.tipo_carroceria_id, "name": c.tipo_carroceria.nombre, "displayName": c.nombre_cliente}
            for c in compat
        ]

    def _sync_compat(self, instance, carrocerias):
        instance.compatibilidades.exclude(
            tipo_carroceria__in=carrocerias,
        ).delete()
        existentes = set(instance.compatibilidades.values_list("tipo_carroceria_id", flat=True))
        CompatibilidadCarroceria.objects.bulk_create([
            CompatibilidadCarroceria(categoria_vehiculo=instance, tipo_carroceria=c)
            for c in carrocerias if c.id not in existentes
        ])

    def _sync_display_names(self, instance, nombres):
        for tipo_carroceria_id, nombre in nombres.items():
            instance.compatibilidades.filter(tipo_carroceria_id=int(tipo_carroceria_id)).update(
                nombre_cliente=(nombre or "").strip(),
            )

    def create(self, validated_data):
        compat = validated_data.pop("_compat_write", None)
        nombres = validated_data.pop("_display_names_write", None)
        instance = super().create(validated_data)
        if compat is not None:
            self._sync_compat(instance, compat)
        if nombres:
            self._sync_display_names(instance, nombres)
        return instance

    def update(self, instance, validated_data):
        compat = validated_data.pop("_compat_write", None)
        nombres = validated_data.pop("_display_names_write", None)
        instance = super().update(instance, validated_data)
        if compat is not None:
            self._sync_compat(instance, compat)
        if nombres:
            self._sync_display_names(instance, nombres)
        return instance
