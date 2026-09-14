"""API v2 · Mi perfil — autoservicio para cualquier usuario del CRM (no
requiere rol específico, solo estar autenticado y no ser un usuario de
portal externo).

    GET   /api/v2/me                  datos propios
    PATCH /api/v2/me                  {fullName?, email?}
    POST  /api/v2/me/change-password  {currentPassword, newPassword}

A propósito NO permite tocar roles/username/active desde acá — eso sigue
siendo exclusivo de "Usuarios y permisos" (apps/dashboard/api/users_views.py).
"""
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import carrier_for, customer_portal_for, role_names


def _set_full_name(user, full_name):
    partes = (full_name or "").strip().split(" ", 1)
    user.first_name = partes[0][:150]
    user.last_name = (partes[1] if len(partes) > 1 else "")[:150]


def _profile_item(user):
    carrier = carrier_for(user)
    cu = customer_portal_for(user)
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.get_full_name() or user.username,
        "email": user.email,
        "roles": role_names(user),
        "isSuperuser": user.is_superuser,
        "dateJoined": user.date_joined.isoformat() if user.date_joined else None,
        "lastLogin": user.last_login.isoformat() if user.last_login else None,
        "carrierName": carrier.nombre if (carrier and carrier.activo) else None,
        "portalCustomerName": (
            (cu.empresa.razon_social if cu.empresa_id else cu.cliente.nombre) if cu else None
        ),
    }


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        return Response(_profile_item(request.user))

    def patch(self, request):
        u = request.user
        d = request.data
        campos = []
        if "fullName" in d:
            _set_full_name(u, d["fullName"])
            campos += ["first_name", "last_name"]
        if "email" in d:
            u.email = (d["email"] or "").strip()
            campos.append("email")
        if campos:
            u.save(update_fields=campos)
        return Response(_profile_item(u))


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return api_exception_handler

    def post(self, request):
        u = request.user
        d = request.data
        current = d.get("currentPassword") or ""
        new = d.get("newPassword") or ""
        if not u.check_password(current):
            raise ValidationError({"currentPassword": "La contraseña actual no es correcta."})
        try:
            validate_password(new, user=u)
        except ValidationError as e:
            raise ValidationError({"newPassword": e.messages})

        u.set_password(new)
        u.save(update_fields=["password"])
        update_session_auth_hash(request, u)  # no cerrar la sesión actual
        return Response({"ok": True})
