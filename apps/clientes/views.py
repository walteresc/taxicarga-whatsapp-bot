from rest_framework import viewsets

from .models import Cliente, Conversacion
from .serializers import ClienteSerializer, ConversacionSerializer


class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    search_fields = ("telefono", "nombre")


class ConversacionViewSet(viewsets.ModelViewSet):
    queryset = Conversacion.objects.select_related("cliente").all()
    serializer_class = ConversacionSerializer

# Create your views here.
