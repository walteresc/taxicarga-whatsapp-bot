"""Base común de los viewsets de la API v2.

Todo viewset v2 hereda de `V2ModelViewSet`: aplica el formato de error uniforme
(apps.api.exceptions) sin tocar el EXCEPTION_HANDLER global, para no alterar las
APIs legacy ni la de la bandeja.
"""
from rest_framework import viewsets

from .exceptions import api_exception_handler
from .pagination import StandardPagination


class V2ModelViewSet(viewsets.ModelViewSet):
    pagination_class = StandardPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_exception_handler(self):
        return api_exception_handler
