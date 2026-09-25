"""API v2 de marca (nombre + logo) — dato de negocio editable desde
Configuración → Marca, sin redeploy. Ver apps/dashboard/models.py::ConfiguracionMarca.

    GET   /api/v2/public/brand    público (login, sidebar, cotizador de invitado)
    GET   /api/v2/brand           igual, para prellenar el form de Configuración
    PATCH /api/v2/brand           {name?, logo?, removeLogo?} — multipart si viene logo

Contrato en inglés (ver docs/PATRON-API-VUE.md) aunque el modelo/campos
internos sigan en español, como el resto del proyecto.
"""
import base64

from django.core.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import HasAnyRole

from ..models import ConfiguracionMarca

_TIPOS_LOGO_VALIDOS = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}


def _payload(marca):
    return {"name": marca.nombre or None, "logoUrl": marca.logo_data_url}


class BrandPublicView(APIView):
    """Solo lectura, sin autenticación — lo consumen login.vue, VerticalNav.vue
    y el cotizador de invitado antes de que exista sesión."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        return Response(_payload(ConfiguracionMarca.get_solo()))


class BrandConfigView(APIView):
    permission_classes = [HasAnyRole("Administrador")]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        return Response(_payload(ConfiguracionMarca.get_solo()))

    def patch(self, request):
        marca = ConfiguracionMarca.get_solo()
        actualizados = []

        if "name" in request.data:
            marca.nombre = (request.data.get("name") or "").strip()
            actualizados.append("nombre")

        if request.data.get("removeLogo"):
            marca.logo_base64 = ""
            marca.logo_content_type = ""
            actualizados += ["logo_base64", "logo_content_type"]

        archivo = request.FILES.get("logo")
        if archivo:
            if archivo.content_type not in _TIPOS_LOGO_VALIDOS:
                raise ValidationError({"logo": "Debe ser PNG, JPG, WEBP o SVG."})
            if archivo.size > ConfiguracionMarca.MAX_LOGO_BYTES:
                raise ValidationError({"logo": "El logo no puede pesar más de 500 KB."})
            marca.logo_base64 = base64.b64encode(archivo.read()).decode("ascii")
            marca.logo_content_type = archivo.content_type
            actualizados += ["logo_base64", "logo_content_type"]

        if actualizados:
            marca.save(update_fields=[*actualizados, "actualizado_en"])
        return Response(_payload(marca))
