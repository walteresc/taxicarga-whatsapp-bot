"""Rastreo público unificado — Fase 0 (2026-09): un cliente ocasional que no
quiere entrar al sistema puede rastrear su carga o encomienda con el
**código** (`CRG-NNNN` / `SVC-NNNN` / `ENC-NNNNN`) + su **teléfono**, en vez
de depender de tener a mano el link con el token.

    POST /api/v2/track/lookup   {code, phone}

El código solo (secuencial, adivinable) nunca alcanza — se exige que el
teléfono ingresado coincida (por los últimos dígitos) con el remitente,
destinatario o cliente de esa carga/envío. Limitado por `ScopedRateThrottle`
para que no sirva de vector de enumeración.

El link con token (`/seguimiento/:token`, `apps.encomiendas`) sigue siendo el
camino de cero fricción — este endpoint es el respaldo para cuando el
cliente no lo tiene a mano, igual que el "número de guía" de un courier.
"""
from django.core.cache import caches
from django.core.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler


class _ThrottleCache(ScopedRateThrottle):
    cache = caches["throttle"]


def _solo_digitos(valor):
    return "".join(ch for ch in (valor or "") if ch.isdigit())


def _coincide(digitos_ingresados, *telefonos):
    for t in telefonos:
        td = _solo_digitos(t)
        if td and digitos_ingresados and td.endswith(digitos_ingresados):
            return True
    return False


class TrackingLookupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [_ThrottleCache]
    throttle_scope = "tracking_lookup"

    def get_exception_handler(self):
        return api_exception_handler

    def post(self, request):
        code = (request.data.get("code") or "").strip().upper()
        digitos = _solo_digitos(request.data.get("phone"))
        if not code or len(digitos) < 4:
            raise ValidationError({"phone": "Ingresá el código y al menos los últimos 4 dígitos de tu teléfono."})

        # Mensaje genérico en todos los casos de no-match (código inexistente
        # o teléfono que no coincide) — no hay que dejarle adivinar a nadie
        # cuál de los dos falló.
        not_found = ValidationError("No encontramos una carga o envío con esos datos. Revisá el código y el teléfono.")

        if code.startswith("ENC-"):
            from apps.encomiendas import services as encomiendas_services
            from apps.encomiendas.models import Envio

            envio = Envio.objects.prefetch_related("eventos").filter(codigo=code).first()
            if not envio or not _coincide(digitos, envio.remitente_telefono, envio.destinatario_telefono):
                raise not_found
            return Response({"type": "shipment", **encomiendas_services.tracking_publico(envio)})

        from apps.servicios import services as servicios_services
        from apps.servicios.models import Servicio

        servicio = Servicio.objects.select_related("cliente").filter(codigo=code).first()
        telefono_cliente = servicio.cliente.telefono if servicio and servicio.cliente_id else ""
        if not servicio or not _coincide(digitos, telefono_cliente):
            raise not_found
        return Response({"type": "cargo", **servicios_services.tracking_publico(servicio)})
