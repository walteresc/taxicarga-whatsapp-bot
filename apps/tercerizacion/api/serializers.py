"""Serializers de la API v2 para transportistas afiliados y sus vehículos."""
from rest_framework import serializers

from apps.catalogo.models import TipoCarroceria, TipoVehiculo
from apps.tercerizacion.models import (
    Transportista, TransportistaConductor, TransportistaVehiculo,
)


class CarrierSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="nombre", max_length=160)
    documentId = serializers.CharField(source="documento", max_length=20, required=False, allow_blank=True, default="")
    phone = serializers.CharField(source="telefono", max_length=30, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    isDriver = serializers.BooleanField(source="es_conductor", required=False, default=False)
    active = serializers.BooleanField(source="activo", required=False, default=True)
    notes = serializers.CharField(source="notas", required=False, allow_blank=True, default="")
    vehicleCount = serializers.IntegerField(source="vehiculos.count", read_only=True)
    useCount = serializers.IntegerField(read_only=True, default=0)
    createdAt = serializers.DateTimeField(source="creado_en", read_only=True)

    class Meta:
        model = Transportista
        fields = (
            "id", "name", "documentId", "phone", "email", "isDriver",
            "active", "notes", "vehicleCount", "useCount", "createdAt",
        )

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["creado_por"] = user if user.is_authenticated else None
        return super().create(validated_data)


class CarrierVehicleSerializer(serializers.ModelSerializer):
    carrierId = serializers.PrimaryKeyRelatedField(source="transportista", queryset=Transportista.objects.all())
    carrierName = serializers.CharField(source="transportista.nombre", read_only=True)
    plate = serializers.CharField(source="placa", max_length=20)
    vehicleTypeId = serializers.PrimaryKeyRelatedField(source="tipo_vehiculo", queryset=TipoVehiculo.objects.all())
    vehicleTypeName = serializers.CharField(source="tipo_vehiculo.nombre", read_only=True)
    bodyTypeId = serializers.PrimaryKeyRelatedField(
        source="tipo_carroceria", queryset=TipoCarroceria.objects.all(),
        required=False, allow_null=True, default=None,
    )
    bodyTypeName = serializers.SerializerMethodField()
    brand = serializers.CharField(source="marca", max_length=80, required=False, allow_blank=True, default="")
    model = serializers.CharField(source="modelo", max_length=80, required=False, allow_blank=True, default="")
    year = serializers.IntegerField(source="anio", required=False, allow_null=True, default=None)
    capacityUsefulTons = serializers.DecimalField(
        source="capacidad_util_ton", max_digits=7, decimal_places=2, required=False, allow_null=True, default=None,
    )
    lengthUsefulM = serializers.DecimalField(
        source="largo_util_m", max_digits=6, decimal_places=2, required=False, allow_null=True, default=None,
    )
    widthUsefulM = serializers.DecimalField(
        source="ancho_util_m", max_digits=6, decimal_places=2, required=False, allow_null=True, default=None,
    )
    heightUsefulM = serializers.DecimalField(
        source="alto_util_m", max_digits=6, decimal_places=2, required=False, allow_null=True, default=None,
    )
    categoryName = serializers.SerializerMethodField()
    active = serializers.BooleanField(source="activo", required=False, default=True)
    notes = serializers.CharField(source="notas", required=False, allow_blank=True, default="")

    def get_bodyTypeName(self, obj):
        return obj.tipo_carroceria.nombre if obj.tipo_carroceria_id else None

    def get_categoryName(self, obj):
        return obj.categoria.nombre if obj.categoria_id else None

    class Meta:
        model = TransportistaVehiculo
        fields = (
            "id", "carrierId", "carrierName", "plate", "vehicleTypeId", "vehicleTypeName",
            "bodyTypeId", "bodyTypeName", "brand", "model", "year",
            "capacityUsefulTons", "lengthUsefulM", "widthUsefulM", "heightUsefulM",
            "categoryName", "active", "notes",
        )

    def validate_plate(self, value):
        qs = TransportistaVehiculo.objects.filter(placa=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un vehículo con esta placa.")
        return value


class CarrierDriverSerializer(serializers.ModelSerializer):
    carrierId = serializers.PrimaryKeyRelatedField(source="transportista", queryset=Transportista.objects.all())
    carrierName = serializers.CharField(source="transportista.nombre", read_only=True)
    name = serializers.CharField(source="nombre", max_length=160)
    documentId = serializers.CharField(source="dni", max_length=20)
    phone = serializers.CharField(source="telefono", max_length=30, required=False, allow_blank=True, default="")
    licenseNumber = serializers.CharField(source="numero_licencia", max_length=40, required=False, allow_blank=True, default="")
    licenseCategory = serializers.CharField(source="categoria_licencia", max_length=20, required=False, allow_blank=True, default="")
    licenseExpiresOn = serializers.DateField(source="fecha_vencimiento_licencia", required=False, allow_null=True, default=None)
    isOwner = serializers.BooleanField(source="es_titular", required=False, default=False)
    active = serializers.BooleanField(source="activo", required=False, default=True)

    class Meta:
        model = TransportistaConductor
        fields = (
            "id", "carrierId", "carrierName", "name", "documentId", "phone",
            "licenseNumber", "licenseCategory", "licenseExpiresOn", "isOwner", "active",
        )

    def validate(self, attrs):
        transportista = attrs.get("transportista") or getattr(self.instance, "transportista", None)
        dni = attrs.get("dni") or getattr(self.instance, "dni", None)
        qs = TransportistaConductor.objects.filter(transportista=transportista, dni=dni)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"documentId": "Este transportista ya tiene un conductor con ese DNI."})
        return attrs
