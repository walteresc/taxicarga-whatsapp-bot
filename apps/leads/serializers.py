from rest_framework import serializers

from .models import Lead


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = "__all__"


class LeadResumenSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source="cliente.nombre", read_only=True)
    cliente_telefono = serializers.CharField(source="cliente.telefono", read_only=True)
    ruta = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            "id",
            "cliente_nombre",
            "cliente_telefono",
            "tipo_servicio",
            "ruta",
            "fecha_servicio",
            "horario_servicio",
            "estado",
            "prioridad",
            "atencion_humana",
            "precio_recomendado",
            "vendedor_asignado",
            "nota_interna",
            "fecha_proximo_seguimiento",
            "fecha_creacion",
        ]

    def get_ruta(self, obj):
        return f"{obj.distrito_origen or '-'} -> {obj.distrito_destino or '-'}"
