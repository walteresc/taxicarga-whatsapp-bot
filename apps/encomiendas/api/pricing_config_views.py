"""API v2 de configuración de Encomiendas/Reparto — comisión sobre
contra-entrega y los costos de recojo/entrega a domicilio para envíos
nacionales (ver ConfiguracionEncomiendas, apps.encomiendas.services). Editable
desde el panel sin redeploy.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import HasAnyRole

from ..models import ConfiguracionEncomiendas

# Mismo criterio que Configuración → Precios / Comisiones de tercerización:
# es un parámetro comercial, no un ajuste técnico del servidor.
_ROLES = ("Administrador", "Gerencia", "Finanzas")

_CAMPOS_DECIMAL = [
    "comision_cod_porcentaje", "costo_recojo_domicilio_nacional", "costo_entrega_domicilio_nacional",
]


def _payload(config):
    return {
        **{campo: float(getattr(config, campo)) for campo in _CAMPOS_DECIMAL},
        "envioIncluidoEnCod": config.envio_incluido_en_cod,
    }


class EncomiendasPricingConfigView(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        return Response(_payload(ConfiguracionEncomiendas.get_solo()))

    def patch(self, request):
        config = ConfiguracionEncomiendas.get_solo()
        data = request.data
        actualizados = []

        for campo in _CAMPOS_DECIMAL:
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

        if "envioIncluidoEnCod" in data:
            config.envio_incluido_en_cod = bool(data["envioIncluidoEnCod"])
            actualizados.append("envio_incluido_en_cod")

        if actualizados:
            config.save(update_fields=[*actualizados, "actualizado_en"])
        return Response(_payload(config))
