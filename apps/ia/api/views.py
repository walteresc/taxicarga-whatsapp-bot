"""API v2 de configuración de IA — elegir qué proveedor/modelo usar por
propósito (extracción/conversación/copiloto) desde el panel, sin redeploy.

La API key NUNCA vive acá: sigue viviendo exclusivamente en `.env` /
infraestructura del servidor (decisión de seguridad — todas las credenciales
del proyecto, OpenAI/WhatsApp/Culqi, están en `.env`, ninguna en base de
datos; meter una acá sería la única excepción, y necesitaría cifrado nuevo
que hoy no existe). Esta pantalla solo elige CUÁL proveedor/modelo usar, y
avisa si al elegido le falta la credencial cargada en el servidor.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import HasAnyRole
from apps.ia.providers import SUPPORTED_PROVIDERS, provider_name_for

from ..models import ConfiguracionIA

# Coincide con SISTEMA_ROLES del router (routes.js, "Configuración → IA") —
# igual que "Configuración → BOT" (apps/whatsapp_bot_v4/api/views.py):
# ajuste técnico del servidor, no una decisión de negocio.
_ROLES = ("Administrador", "Admin de sistema")

_CAMPO_POR_KEY = {
    "defaultProvider": "proveedor_default",
    "extractionProvider": "proveedor_extraccion",
    "conversationProvider": "proveedor_conversacion",
    "copilotProvider": "proveedor_copiloto",
}


def _payload(config):
    return {
        "defaultProvider": config.proveedor_default,
        "extractionProvider": config.proveedor_extraccion,
        "conversationProvider": config.proveedor_conversacion,
        "copilotProvider": config.proveedor_copiloto,
        "openaiModel": config.modelo_openai,
        "deepseekModel": config.modelo_deepseek,
        # Lo que realmente se usaría ahora mismo, ya resuelto (panel → .env
        # → default de settings.py) — para que la pantalla no obligue a
        # adivinar qué gana si se dejan campos en blanco.
        "effective": {
            "extraction": provider_name_for("extraction"),
            "conversation": provider_name_for("conversation"),
            "copilot": provider_name_for("copilot"),
        },
        "serverDefaults": {
            "provider": settings.AI_PROVIDER,
            "openaiModel": settings.OPENAI_MODEL,
            "deepseekModel": settings.DEEPSEEK_MODEL,
        },
        "hasOpenaiKey": bool(settings.OPENAI_API_KEY),
        "hasDeepseekKey": bool(settings.DEEPSEEK_API_KEY),
    }


class AIConfigView(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        return Response(_payload(ConfiguracionIA.get_solo()))

    def patch(self, request):
        config = ConfiguracionIA.get_solo()
        data = request.data

        for key, campo in _CAMPO_POR_KEY.items():
            if key not in data:
                continue
            valor = (data.get(key) or "").strip().lower()
            if valor and valor not in SUPPORTED_PROVIDERS:
                raise ValidationError({key: f"Proveedor inválido: {valor}."})
            setattr(config, campo, valor)

        if "openaiModel" in data:
            config.modelo_openai = (data.get("openaiModel") or "").strip()
        if "deepseekModel" in data:
            config.modelo_deepseek = (data.get("deepseekModel") or "").strip()

        config.save()
        return Response(_payload(config))
