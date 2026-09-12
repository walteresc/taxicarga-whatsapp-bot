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
            # Gerencia es superadministrador (decisión del usuario, 2026-09-12):
            # pasa cualquier HasAnyRole del proyecto, no solo los que la listan
            # explícitamente — así no hay que auditar cada _ROLES del backend
            # cada vez que se agrega una pantalla nueva.
            if user.groups.filter(name="Gerencia").exists():
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


def carrier_for(user):
    """La ficha `Transportista` de un usuario del Portal del Transportista, o None."""
    if not user or not user.is_authenticated:
        return None
    return getattr(user, "transportista_perfil", None)


class IsCarrier(BasePermission):
    message = "Acceso exclusivo del Portal del Transportista."

    def has_permission(self, request, view):
        t = carrier_for(request.user)
        return t is not None and t.activo


def customer_portal_for(user):
    """El `ClienteUsuario` de un usuario del Portal del Cliente, o None."""
    if not user or not user.is_authenticated:
        return None
    cu = getattr(user, "cliente_portal", None)
    return cu if (cu and cu.activo) else None


class IsPortalCustomer(BasePermission):
    message = "Acceso exclusivo del Portal del Cliente."

    def has_permission(self, request, view):
        return customer_portal_for(request.user) is not None


def role_names(user):
    """Lista de roles (grupos) del usuario, en inglés canónico interno del
    proyecto (que ya está en español). El superusuario obtiene 'Administrador'
    de forma implícita para que el front no tenga que tratarlo aparte.

    Gerencia (decisión del usuario, 2026-09-12) es un "superadministrador":
    tiene acceso a todo lo que tiene Administrador, en el menú y en cada
    `HasAnyRole`/`role_required` del backend — no hay que listar 'Gerencia'
    en cada permiso del proyecto, alcanza con este alias acá."""
    if not user or not user.is_authenticated:
        return []
    names = list(user.groups.values_list("name", flat=True))
    if user.is_superuser and "Administrador" not in names:
        names.append("Administrador")
    if "Gerencia" in names and "Administrador" not in names:
        names.append("Administrador")
    return names
