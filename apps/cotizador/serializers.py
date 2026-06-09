from rest_framework import serializers

from .models import Cotizacion, ServicioHistorico


class ServicioHistoricoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicioHistorico
        fields = "__all__"


class CotizacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cotizacion
        fields = "__all__"
