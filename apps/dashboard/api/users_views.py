"""API v2 · Usuarios y permisos (F4).

    GET   /api/v2/roles/                 roles asignables (grupos canónicos)
    GET   /api/v2/users/                 lista (search, role, active)
    POST  /api/v2/users/                 alta {username, password, fullName?, email?, roles?}
    GET   /api/v2/users/<pk>/
    PATCH /api/v2/users/<pk>/            {roles?: [...], active?: bool, fullName?, email?, password?}

Solo 'Administrador' / 'Admin de sistema'. Un superusuario de Django no se
puede editar desde acá salvo que quien edita también sea superusuario, y nadie
puede quitarse a sí mismo 'Admin de sistema' (anti-lockout). Nunca se crea un
usuario con is_staff/is_superuser desde acá.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.pagination import StandardPagination
from apps.api.permissions import HasAnyRole, ROLES_ADMIN_SISTEMA

User = get_user_model()

# Roles canónicos + una glosa corta para la UI. El orden es el de la pantalla.
ROLES = [
    ("Administrador", "Acceso total (superrol de compatibilidad)"),
    ("Gerencia", "Negocio: márgenes, costos, precios, reportes"),
    ("Admin de sistema", "Usuarios, roles, integraciones, config técnica"),
    ("Supervisor", "Supervisa operación y comercial"),
    ("Asesor de Ventas", "Pipeline comercial, cotiza y atiende"),
    ("Despacho", "Pizarra, programación, publicar y adjudicar"),
    ("Finanzas", "Pagos, planilla, facturación, cobros"),
    ("Conductor", "App de campo: sus servicios"),
    ("Ayudante", "App de campo: sus servicios"),
]
_ROLE_NAMES = [r[0] for r in ROLES]


def _clean_roles(raw):
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValidationError({"roles": "Se esperaba una lista de roles."})
    invalidos = [r for r in raw if r not in _ROLE_NAMES]
    if invalidos:
        raise ValidationError({"roles": f"Rol(es) no válido(s): {', '.join(invalidos)}"})
    return raw


def _check_password(pwd, user=None):
    try:
        validate_password(pwd, user=user)
    except ValidationError as e:
        raise ValidationError({"password": e.messages})


def _set_full_name(user, full_name):
    partes = (full_name or "").strip().split(" ", 1)
    user.first_name = partes[0][:150]
    user.last_name = (partes[1] if len(partes) > 1 else "")[:150]


def user_item(u):
    return {
        "id": u.id,
        "username": u.username,
        "fullName": u.get_full_name(),
        "email": u.email,
        "active": u.is_active,
        "isSuperuser": u.is_superuser,
        "roles": sorted(u.groups.values_list("name", flat=True)),
        "lastLogin": u.last_login.isoformat() if u.last_login else None,
    }


class _Base(APIView):
    permission_classes = [HasAnyRole(*ROLES_ADMIN_SISTEMA)]

    def get_exception_handler(self):
        return api_exception_handler


class RoleListView(_Base):
    def get(self, request):
        return Response([{"name": n, "description": d} for n, d in ROLES])


class UserListView(_Base):
    def get(self, request):
        p = request.query_params
        qs = User.objects.prefetch_related("groups").order_by("username")
        search = (p.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )
        if p.get("role"):
            qs = qs.filter(groups__name=p["role"])
        if p.get("active") in ("true", "false"):
            qs = qs.filter(is_active=p["active"] == "true")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([user_item(u) for u in page])

    def post(self, request):
        d = request.data
        username = (d.get("username") or "").strip()
        password = d.get("password") or ""
        if not username:
            raise ValidationError({"username": "Ingresá un nombre de usuario."})
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError({"username": "Ya existe un usuario con ese nombre."})
        roles = _clean_roles(d.get("roles"))
        _check_password(password)

        user = User.objects.create_user(
            username=username, password=password,
            email=(d.get("email") or "").strip(),
            is_staff=False, is_superuser=False, is_active=True,
        )
        _set_full_name(user, d.get("fullName"))
        user.save(update_fields=["first_name", "last_name"])
        if roles:
            user.groups.set(Group.objects.filter(name__in=roles))
        return Response(user_item(user), status=201)


class UserDetailView(_Base):
    def get(self, request, pk):
        return Response(user_item(get_object_or_404(User.objects.prefetch_related("groups"), pk=pk)))

    def patch(self, request, pk):
        u = get_object_or_404(User, pk=pk)
        actor = request.user
        if u.is_superuser and not actor.is_superuser:
            raise ValidationError("No puedes editar a un superusuario de Django.")

        d = request.data
        if "roles" in d:
            nuevos = _clean_roles(d["roles"])
            if u.id == actor.id and not actor.is_superuser:
                tenia = set(u.groups.values_list("name", flat=True)) & set(ROLES_ADMIN_SISTEMA)
                if tenia and not (set(nuevos) & set(ROLES_ADMIN_SISTEMA)):
                    raise ValidationError("No puedes quitarte tu propio rol de administración.")
            u.groups.set(Group.objects.filter(name__in=nuevos))

        campos = []
        if "active" in d:
            if u.id == actor.id and not d["active"]:
                raise ValidationError("No puedes desactivar tu propia cuenta.")
            u.is_active = bool(d["active"])
            campos.append("is_active")
        if "fullName" in d:
            _set_full_name(u, d["fullName"])
            campos += ["first_name", "last_name"]
        if "email" in d:
            u.email = (d["email"] or "").strip()
            campos.append("email")
        if d.get("password"):
            _check_password(d["password"], user=u)
            u.set_password(d["password"])
            campos.append("password")
        if campos:
            u.save(update_fields=campos)

        return Response(user_item(get_object_or_404(User.objects.prefetch_related("groups"), pk=pk)))
