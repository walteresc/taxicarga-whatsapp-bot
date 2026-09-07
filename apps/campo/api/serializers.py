"""Serializers de la API v2 para Personal. Claves en inglés vía `source=`.

El renombrado de campos usa DRIVER_FIELDS / ASSISTANT_FIELDS de mappers.py de
forma implícita (cada `source=` es la contraparte declarada allí). El test de
ida y vuelta en tests_api.py verifica que serializer y mapa no se desincronizan.
"""
from rest_framework import serializers

from apps.campo.models import Ayudante, Conductor

from .mappers import LICENSE_CATEGORY


class DriverSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="nombre", max_length=160)
    documentId = serializers.CharField(source="dni", max_length=20)
    phone = serializers.CharField(source="telefono", max_length=30)
    licenseNumber = serializers.CharField(
        source="numero_licencia", max_length=40, required=False, allow_blank=True, default="",
    )
    licenseCategory = serializers.ChoiceField(
        source="categoria_licencia", choices=sorted(LICENSE_CATEGORY),
        required=False, allow_blank=True, default="",
    )
    licenseExpiresOn = serializers.DateField(
        source="fecha_vencimiento_licencia", required=False, allow_null=True, default=None,
    )
    active = serializers.BooleanField(source="activo", required=False, default=True)
    notes = serializers.CharField(
        source="observaciones", required=False, allow_blank=True, default="",
    )

    class Meta:
        model = Conductor
        fields = (
            "id", "name", "documentId", "phone", "licenseNumber",
            "licenseCategory", "licenseExpiresOn", "active", "notes",
        )

    def validate_documentId(self, value):
        qs = Conductor.objects.filter(dni=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un conductor con este documento.")
        return value


class AssistantSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="nombre", max_length=160)
    documentId = serializers.CharField(source="dni", max_length=20)
    phone = serializers.CharField(source="telefono", max_length=30)
    active = serializers.BooleanField(source="activo", required=False, default=True)
    notes = serializers.CharField(
        source="observaciones", required=False, allow_blank=True, default="",
    )

    class Meta:
        model = Ayudante
        fields = ("id", "name", "documentId", "phone", "active", "notes")

    def validate_documentId(self, value):
        qs = Ayudante.objects.filter(dni=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un ayudante con este documento.")
        return value
