"""Serializers de la API v2 para Flota. Claves inglesas vía `source=`.

Contraparte de VEHICLE_FIELDS / MAINTENANCE_FIELDS de mappers.py; el test de ida
y vuelta en tests_api.py verifica que no se desincronizan.
"""
from rest_framework import serializers

from apps.campo.models import Vehiculo
from apps.flota.models import MantenimientoVehiculo


class VehicleSerializer(serializers.ModelSerializer):
    plate = serializers.CharField(source="placa", max_length=20)
    brand = serializers.CharField(source="marca", max_length=80)
    model = serializers.CharField(source="modelo", max_length=80)
    year = serializers.IntegerField(source="anio", required=False, allow_null=True, default=None)
    capacityTons = serializers.DecimalField(
        source="capacidad_toneladas", max_digits=6, decimal_places=2,
    )
    capacityM3 = serializers.DecimalField(
        source="capacidad_m3", max_digits=8, decimal_places=2,
        required=False, allow_null=True, default=None,
    )
    soatExpiresOn = serializers.DateField(
        source="fecha_vencimiento_soat", required=False, allow_null=True, default=None,
    )
    technicalReviewExpiresOn = serializers.DateField(
        source="fecha_vencimiento_rtv", required=False, allow_null=True, default=None,
    )
    fireExtinguisherExpiresOn = serializers.DateField(
        source="fecha_vencimiento_extintor", required=False, allow_null=True, default=None,
    )
    active = serializers.BooleanField(source="activo", required=False, default=True)
    notes = serializers.CharField(
        source="observaciones", required=False, allow_blank=True, default="",
    )

    class Meta:
        model = Vehiculo
        fields = (
            "id", "plate", "brand", "model", "year", "capacityTons", "capacityM3",
            "soatExpiresOn", "technicalReviewExpiresOn", "fireExtinguisherExpiresOn",
            "active", "notes",
        )

    def validate_plate(self, value):
        qs = Vehiculo.objects.filter(placa=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un vehículo con esta placa.")
        return value


class MaintenanceSerializer(serializers.ModelSerializer):
    vehicleId = serializers.PrimaryKeyRelatedField(
        source="vehiculo", queryset=Vehiculo.objects.all(),
    )
    vehiclePlate = serializers.CharField(source="vehiculo.placa", read_only=True)
    performedOn = serializers.DateField(source="fecha_mantenimiento")
    odometer = serializers.IntegerField(source="kilometraje_actual", min_value=0)
    nextServiceOdometer = serializers.IntegerField(
        source="proximo_mantenimiento_km", min_value=0,
    )
    work = serializers.CharField(source="descripcion")
    notes = serializers.CharField(
        source="observaciones", required=False, allow_blank=True, default="",
    )

    class Meta:
        model = MantenimientoVehiculo
        fields = (
            "id", "vehicleId", "vehiclePlate", "performedOn", "odometer",
            "nextServiceOdometer", "work", "notes",
        )

    def validate(self, attrs):
        siguiente = attrs.get("proximo_mantenimiento_km")
        actual = attrs.get("kilometraje_actual")
        if siguiente is not None and actual is not None and siguiente <= actual:
            raise serializers.ValidationError({
                "nextServiceOdometer": "Debe ser mayor que el kilometraje actual.",
            })
        return attrs
