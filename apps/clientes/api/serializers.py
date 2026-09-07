"""Serializer de la API v2 para Clientes. Claves inglesas vía `source=`.

El teléfono se normaliza a E.164 en `Cliente.save()`; la unicidad se valida aquí
comparando el valor ya normalizado (para que "995403320" y "+51995403320"
colisionen). Campos de solo lectura para la UI: contactId, hasRealPhone,
displayName, createdAt.
"""
from django.db.models import Q
from rest_framework import serializers

from apps.clientes.models import Cliente
from apps.clientes.phone_normalizer import normalize_phone


class CustomerSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="nombre", max_length=160, required=False, allow_blank=True, default="")
    phone = serializers.CharField(source="telefono", max_length=30)
    documentId = serializers.CharField(source="documento", max_length=20, required=False, allow_blank=True, default="")
    email = serializers.EmailField(source="correo", max_length=200, required=False, allow_blank=True, default="")
    taxId = serializers.CharField(source="ruc", max_length=20, required=False, allow_blank=True, default="")
    businessName = serializers.CharField(source="razon_social", max_length=200, required=False, allow_blank=True, default="")
    active = serializers.BooleanField(source="is_active", required=False, default=True)

    # Solo lectura — contexto para la UI.
    displayName = serializers.CharField(source="profile_name", read_only=True)
    contactId = serializers.CharField(source="contact_phone", read_only=True)
    hasRealPhone = serializers.BooleanField(source="has_real_phone", read_only=True)
    isTransportista = serializers.BooleanField(source="es_transportista", read_only=True)
    createdAt = serializers.DateTimeField(source="fecha_creacion", read_only=True)

    class Meta:
        model = Cliente
        fields = (
            "id", "name", "phone", "documentId", "email", "taxId", "businessName",
            "active", "displayName", "contactId", "hasRealPhone", "isTransportista",
            "createdAt",
        )

    def validate_phone(self, value):
        raw = (value or "").strip()
        norm = normalize_phone(raw)
        candidato = norm["normalized_e164"] if norm["is_valid"] else raw
        qs = Cliente.objects.filter(Q(telefono=candidato) | Q(phone_e164=candidato))
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un cliente con este teléfono.")
        return raw
