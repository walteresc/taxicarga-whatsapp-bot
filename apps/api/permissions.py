"""Permisos por rol para la API v2.

Uso en un viewset:

    from apps.api.permissions import HasAnyRole

    class DriverViewSet(viewsets.ModelViewSet):
        permission_classes = [HasAnyRole("Administrador", "Supervisor")]

Un superusuario siempre pasa. Los nombres de rol son los grupos canónicos:
"Administrador", "Supervisor", "Asesor de Ventas", "Conductor", "Ayudante".
"""
from rest_framework.permissions import BasePermission


def HasAnyRole(*roles):
    lookup = set(roles)

    class _HasAnyRole(BasePermission):
        message = "No tienes el rol necesario para esta operación."

        def has_permission(self, request, view):
            user = request.user
            if not user or not user.is_authenticated:
                return False
            if user.is_superuser:
                return True
            return user.groups.filter(name__in=lookup).exists()

    _HasAnyRole.__name__ = f"HasAnyRole_{'_'.join(sorted(lookup))}"
    return _HasAnyRole


# Roles que pueden ver costos de tercerización y el margen (venta − costo).
# Decisión de negocio (F4): el Asesor de Ventas ve la venta pero no el costo de compra.
ROLES_MARGEN = ("Administrador", "Gerencia", "Supervisor", "Despacho", "Finanzas")

# Roles que administran usuarios y permisos.
ROLES_ADMIN_SISTEMA = ("Administrador", "Admin de sistema")


def puede_ver_margen(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=ROLES_MARGEN).exists()


def role_names(user):
    """Lista de roles (grupos) del usuario, en inglés canónico interno del
    proyecto (que ya está en español). El superusuario obtiene 'Administrador'
    de forma implícita para que el front no tenga que tratarlo aparte."""
    if not user or not user.is_authenticated:
        return []
    names = list(user.groups.values_list("name", flat=True))
    if user.is_superuser and "Administrador" not in names:
        names.append("Administrador")
    return names
