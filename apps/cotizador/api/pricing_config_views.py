"""API v2 de configuración de precios — los parámetros del cálculo por
reglas base (`apps/cotizador/pricing.py::fallback_price_for_lead`), editables
desde el panel sin redeploy. Es el cálculo que se usa cuando no hay
suficientes históricos parecidos para cotizar por mediana — antes vivían
hardcodeados como constantes de Python.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import HasAnyRole

from ..models import ConfiguracionPrecios

# Mismo criterio que "Configuración → Comisiones de tercerización": es un
# parámetro comercial/de precios, no un ajuste técnico del servidor.
_ROLES = ("Administrador", "Gerencia", "Finanzas")

_CAMPOS = [
    "base_mudanza", "base_carga", "base_traslado_pequeno", "base_oficina", "base_corporativo", "base_otros",
    "costo_por_kg", "costo_por_m3", "costo_por_piso_sin_ascensor",
    "costo_personal_carga", "costo_desarmado", "costo_objeto_pesado", "costo_camion_no_llega",
    "costo_embalaje_basico", "costo_embalaje_completo", "costo_embalaje_full",
    "costo_descripcion_media", "costo_descripcion_grande", "costo_descripcion_muy_grande",
    "costo_caminata_por_bloque", "rango_min_pct", "rango_max_pct",
]


def _payload(config):
    return {campo: float(getattr(config, campo)) for campo in _CAMPOS}


class PricingConfigView(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        return Response(_payload(ConfiguracionPrecios.get_solo()))

    def patch(self, request):
        config = ConfiguracionPrecios.get_solo()
        data = request.data
        actualizados = []

        for campo in _CAMPOS:
            if campo not in data:
                continue
            valor = data.get(campo)
            try:
                decimal_valor = Decimal(str(valor))
            except (InvalidOperation, TypeError, ValueError):
                raise ValidationError({campo: "Debe ser un número."})
            if decimal_valor < 0:
                raise ValidationError({campo: "No puede ser negativo."})
            setattr(config, campo, decimal_valor)
            actualizados.append(campo)

        if actualizados:
            config.save(update_fields=[*actualizados, "actualizado_en"])
        return Response(_payload(config))
