"""API v2 de configuración del bot. Expone el estado de los 3 interruptores
(clientes, transportistas, operativo) para la pantalla de configuración en
Vue. Solo las ACCIONES del bot operativo viven aquí — pausar/reanudar el bot
de clientes y el de transportistas se hace desde los endpoints ya existentes
(`/webhooks/api/control/...` y `/dashboard/tercerizacion/bot/...`, usados por
la bandeja de entrada) para no duplicar esa lógica ni arriesgar su
comportamiento. Este módulo solo LEE esos dos campos.
"""
from django.conf import settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import HasAnyRole

from ..models import BotGlobalConfig

_ROLES = ("Administrador", "Supervisor", "Asesor de Ventas")


def _config():
    config = BotGlobalConfig.objects.first()
    if not config:
        config = BotGlobalConfig.objects.create()
    return config


def _status_payload(config):
    return {
        "customers": {
            "paused": config.is_paused,
            "pausedAt": config.paused_at.isoformat() if config.paused_at else None,
        },
        "carriers": {
            "paused": config.transportistas_paused,
            "pausedAt": config.transportistas_paused_at.isoformat() if config.transportistas_paused_at else None,
            "enabledInDeployment": settings.TRANSPORTISTA_BOT_ENABLED,
        },
        "operations": {
            "paused": config.operativo_paused,
            "pausedAt": config.operativo_paused_at.isoformat() if config.operativo_paused_at else None,
        },
    }


class _Base(APIView):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler


class BotStatusView(_Base):
    def get(self, request):
        return Response(_status_payload(_config()))


class BotOperationsPauseView(_Base):
    def post(self, request):
        config = _config()
        config.operativo_paused = True
        config.operativo_paused_at = timezone.now()
        config.save(update_fields=["operativo_paused", "operativo_paused_at"])
        return Response(_status_payload(config))


class BotOperationsResumeView(_Base):
    def post(self, request):
        config = _config()
        config.operativo_paused = False
        config.operativo_paused_at = None
        config.save(update_fields=["operativo_paused", "operativo_paused_at"])
        return Response(_status_payload(config))
