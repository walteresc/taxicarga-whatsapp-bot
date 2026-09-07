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
    compatibleBodyTypeIds = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=TipoCarroceria.objects.all(), source="_compat_write",
    )
    compatibleBodyTypes = serializers.SerializerMethodField()

    class Meta:
        model = TipoVehiculo
        fields = (
            "id", "code", "name", "icon", "enabled", "order",
            "compatibleBodyTypeIds", "compatibleBodyTypes",
        )

    def get_compatibleBodyTypes(self, obj):
        return [
            {"id": c.tipo_carroceria_id, "name": c.tipo_carroceria.nombre}
            for c in obj.compatibilidades.select_related("tipo_carroceria").all()
        ]

    def validate_code(self, value):
        qs = TipoVehiculo.objects.filter(codigo=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un tipo con este código.")
        return value

    def _sync_compat(self, instance, carrocerias):
        instance.compatibilidades.exclude(
            tipo_carroceria__in=carrocerias,
        ).delete()
        existentes = set(instance.compatibilidades.values_list("tipo_carroceria_id", flat=True))
        CompatibilidadCarroceria.objects.bulk_create([
            CompatibilidadCarroceria(tipo_vehiculo=instance, tipo_carroceria=c)
            for c in carrocerias if c.id not in existentes
        ])

    def create(self, validated_data):
        compat = validated_data.pop("_compat_write", None)
        instance = super().create(validated_data)
        if compat is not None:
            self._sync_compat(instance, compat)
        return instance

    def update(self, instance, validated_data):
        compat = validated_data.pop("_compat_write", None)
        instance = super().update(instance, validated_data)
        if compat is not None:
            self._sync_compat(instance, compat)
        return instance


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

    class Meta:
        model = CategoriaVehiculo
        fields = (
            "id", "vehicleTypeId", "vehicleTypeName", "name", "category",
            "minTons", "maxTons", "order", "enabled",
        )
