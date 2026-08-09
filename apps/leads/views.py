import hashlib

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from decimal import Decimal, InvalidOperation

from apps.cotizador.commercial import guardar_borrador
from apps.cotizador.delivery import queue_revision_whatsapp
from apps.cotizador.services import cotizar_lead
from apps.whatsapp.domain import enviar_a_cotizar, obtener_o_crear_conversacion
from .models import Lead
from .serializers import LeadResumenSerializer, LeadSerializer


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.select_related("cliente", "vendedor_asignado").all()
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    @action(detail=False, methods=["get"])
    def pendientes(self, request):
        leads = self.get_queryset().filter(
            estado__in=[Lead.NUEVO, Lead.EN_CONVERSACION, Lead.DATOS_INCOMPLETOS]
        )
        serializer = LeadResumenSerializer(leads, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def cotizados(self, request):
        leads = self.get_queryset().filter(estado=Lead.COTIZADO)
        serializer = LeadResumenSerializer(leads, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def asignarme(self, request, pk=None):
        lead = self.get_object()
        if not request.user.is_authenticated:
            return Response({"detail": "Autenticacion requerida."}, status=status.HTTP_401_UNAUTHORIZED)
        lead.vendedor_asignado = request.user
        lead.estado = Lead.ASIGNADO
        lead.save(update_fields=["vendedor_asignado", "estado"])
        return Response(LeadSerializer(lead).data)

    @action(detail=True, methods=["post"])
    def registrar_nota(self, request, pk=None):
        lead = self.get_object()
        nota = str(request.data.get("nota", "")).strip()
        if not nota:
            return Response({"detail": "La nota es requerida."}, status=status.HTTP_400_BAD_REQUEST)
        timestamp = timezone.localtime().strftime("%Y-%m-%d %H:%M")
        lead.nota_interna = f"{lead.nota_interna}\n[{timestamp}] {nota}".strip()
        lead.fecha_ultimo_seguimiento = timezone.now()
        lead.save(update_fields=["nota_interna", "fecha_ultimo_seguimiento"])
        return Response(LeadSerializer(lead).data)

    @action(detail=True, methods=["post"])
    def cambiar_estado(self, request, pk=None):
        lead = self.get_object()
        nuevo_estado = request.data.get("estado")
        estados_validos = {estado for estado, _ in Lead.ESTADOS}
        if nuevo_estado not in estados_validos:
            return Response({"detail": "Estado invalido."}, status=status.HTTP_400_BAD_REQUEST)
        lead.estado = nuevo_estado
        if nuevo_estado in {Lead.CERRADO, Lead.PERDIDO}:
            lead.fecha_cierre = timezone.now()
        lead.save(update_fields=["estado", "fecha_cierre"])
        return Response(LeadSerializer(lead).data)

    @action(detail=True, methods=["post"])
    def registrar_seguimiento(self, request, pk=None):
        lead = self.get_object()
        lead.fecha_ultimo_seguimiento = timezone.now()
        lead.save(update_fields=["fecha_ultimo_seguimiento"])
        return Response(LeadSerializer(lead).data)

    @action(detail=True, methods=["post"])
    def registrar_cotizacion(self, request, pk=None):
        lead = self.get_object()
        quoted_price = _decimal_or_none(request.data.get("precio_cotizado"))
        if quoted_price is None or quoted_price <= 0:
            return Response({"detail": "Precio cotizado invalido."}, status=status.HTTP_400_BAD_REQUEST)

        message = str(request.data.get("mensaje", "")).strip() or _default_quote_message(lead, quoted_price)
        conversation = obtener_o_crear_conversacion(lead)
        solicitud = enviar_a_cotizar(
            conversation.id, request.user, "Cotización registrada mediante API legacy", []
        )
        technical = lead.cotizaciones.order_by("-fecha_creacion").first() or cotizar_lead(lead)
        supplied_key = str(request.data.get("idempotency_key") or request.META.get("HTTP_IDEMPOTENCY_KEY") or "")
        fingerprint = supplied_key or hashlib.sha256(
            f"{lead.id}|{quoted_price}|{message}".encode()
        ).hexdigest()
        _quote, revision = guardar_borrador(
            solicitud, request.user, quoted_price,
            cotizacion_tecnica=technical,
            source_key=f"legacy-register-quote:{fingerprint}",
            precio_sugerido_min=technical.precio_min,
            precio_sugerido_max=technical.precio_max,
            mensaje_whatsapp=message,
        )
        queue_revision_whatsapp(revision.id, actor=request.user)
        return Response(LeadSerializer(lead).data)


def _decimal_or_none(value):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _default_quote_message(lead, price):
    route = ""
    if lead.distrito_origen or lead.distrito_destino:
        route = f" de {lead.distrito_origen or 'origen'} a {lead.distrito_destino or 'destino'}"
    return (
        f"Listo, para el servicio{route}, la cotizacion queda en S/ {price:.0f}. "
        "Incluye movilidad y personal segun lo conversado. Si le parece bien, coordinamos la hora."
    )

# Create your views here.
