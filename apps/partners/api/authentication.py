from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from apps.partners.models import ApiKey


class ApiKeyAuthentication(BaseAuthentication):
    """`Authorization: Bearer <prefix>.<secreto>`. Deja `request.auth` = la
    ApiKey resuelta; `request.user` queda anónimo (no hay usuario Django)."""

    keyword = "Bearer"

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith(f"{self.keyword} "):
            return None
        token = header[len(self.keyword) + 1:].strip()
        key = ApiKey.resolver(token)
        if not key:
            raise AuthenticationFailed("Llave de API inválida o inactiva.")
        return (AnonymousUser(), key)


class HasApiKey(BasePermission):
    def has_permission(self, request, view):
        return getattr(request, "auth", None) is not None
