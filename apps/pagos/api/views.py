"""API v2 · Pagos.

Público (sin auth):
    GET  /api/v2/pay/<token>            datos de la orden para el checkout
    POST /api/v2/pay/<token>/charge     {sourceToken, email}
    POST /api/v2/payments/webhook/<provider>

Interno:
    POST /api/v2/pipeline/bookings/<pk>/payment-link   {installmentId?, amount?}
"""
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import HasAnyRole
from apps.pagos import services
from apps.pagos.models import OrdenPago
from apps.pagos.pasarelas import build_pasarela

_ROLES_LINK = ("Administrador", "Gerencia", "Supervisor", "Despacho", "Finanzas", "Asesor de Ventas")


def _order_public(orden):
    s = orden.servicio
    return {
        "token": orden.token,
        "state": orden.estado,
        "amount": float(orden.monto),
        "currency": orden.moneda,
        "concept": orden.concepto,
        "serviceCode": s.codigo,
        "route": f"{s.distrito_origen or '?'} → {s.distrito_destino or '?'}",
        "customerName": s.cliente.nombre if s.cliente_id else "",
        "payable": orden.pagable,
        "gateway": build_pasarela(orden.pasarela).config_publica,
        "error": orden.detalle_error or None,
    }


class _PublicBase(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_exception_handler(self):
        return api_exception_handler


class PublicOrderView(_PublicBase):
    def get(self, request, token):
        return Response(_order_public(get_object_or_404(OrdenPago, token=token)))


@method_decorator(csrf_exempt, name="dispatch")
class PublicChargeView(_PublicBase):
    def post(self, request, token):
        orden = get_object_or_404(OrdenPago, token=token)
        orden = services.procesar_cargo(
            orden,
            source_token=(request.data.get("sourceToken") or "").strip(),
            email=(request.data.get("email") or "").strip(),
        )
        return Response(_order_public(orden))


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(_PublicBase):
    def post(self, request, provider):
        pasarela = build_pasarela(provider)
        evento = pasarela.verificar_webhook(request.META, request.body)
        if evento is None:
            return Response({"ok": False, "detail": "firma inválida"}, status=400)
        parsed = pasarela.parsear_evento(evento)
        if parsed:
            services.confirmar_por_webhook(pasarela.nombre, parsed[0], parsed[1])
        return Response({"ok": True})


class BookingPaymentLinkView(APIView):
    permission_classes = [HasAnyRole(*_ROLES_LINK)]

    def get_exception_handler(self):
        return api_exception_handler

    def post(self, request, pk):
        from apps.servicios.models import Servicio
        servicio = get_object_or_404(Servicio, pk=pk)
        orden = services.crear_orden(
            servicio,
            cuota_id=request.data.get("installmentId"),
            monto=request.data.get("amount"),
            concepto=request.data.get("concept"),
            usuario=request.user,
            origen="link",
        )
        return Response({
            "token": orden.token,
            "url": f"/pagar/{orden.token}",
            "amount": float(orden.monto),
            "state": orden.estado,
        })
