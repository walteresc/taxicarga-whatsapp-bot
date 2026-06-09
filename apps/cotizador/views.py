from rest_framework import viewsets

from .models import Cotizacion, ServicioHistorico
from .serializers import CotizacionSerializer, ServicioHistoricoSerializer


class ServicioHistoricoViewSet(viewsets.ModelViewSet):
    queryset = ServicioHistorico.objects.all()
    serializer_class = ServicioHistoricoSerializer


class CotizacionViewSet(viewsets.ModelViewSet):
    queryset = Cotizacion.objects.select_related("lead", "lead__cliente").all()
    serializer_class = CotizacionSerializer

# Create your views here.
