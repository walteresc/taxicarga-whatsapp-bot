from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from decimal import Decimal, InvalidOperation

from apps.clientes.models import Conversacion
from apps.whatsapp.services import send_whatsapp_message
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
        send_whatsapp_message(lead.cliente.telefono, message)
        Conversacion.objects.create(
            cliente=lead.cliente,
            mensaje_entrada="",
            mensaje_salida=message,
            canal=Conversacion.CANAL_WHATSAPP,
        )
        lead.precio_cotizado = quoted_price
        lead.estado = Lead.COTIZADO
        lead.atencion_humana = True
        lead.fecha_ultimo_seguimiento = timezone.now()
        lead.save(
            update_fields=[
                "precio_cotizado",
                "estado",
                "atencion_humana",
                "fecha_ultimo_seguimiento",
            ]
        )
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
