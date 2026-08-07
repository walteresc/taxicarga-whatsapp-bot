from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from functools import wraps


def user_in_group(user, group_name):
    if not user.is_authenticated:
        return False
    return user.groups.filter(name=group_name).exists()


def has_role(user, roles):
    if not user.is_authenticated:
        return False
    if isinstance(roles, str):
        roles = [roles]
    # Corregido para que administrador tenga acceso total
    if "Administrador" in roles and user.is_superuser:
        return True
    return user.groups.filter(name__in=roles).exists() or user.is_superuser


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not has_role(request.user, roles):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def can_manage_campo(user):
    # Asesor de Ventas puede gestionar Campo, Supervisor también
    return has_role(user, ["Administrador", "Supervisor", "Asesor de Ventas"])


def can_manage_pizarra(user):
    # Igual permisos para pizarra
    return has_role(user, ["Administrador", "Supervisor", "Asesor de Ventas"])


def can_view_assigned_services(user):
    # Conductor y ayudante solo viendo sus servicios
    return has_role(user, ["Conductor", "Ayudante"])


def can_driver_update_status(user):
    # Solo conductor puede actualizar estado
    return user_in_group(user, "Conductor")


def can_manage_leads(user):
    # Solo administradores, supervisores y asesores
    return has_role(user, ["Administrador", "Supervisor", "Asesor de Ventas"])


def can_manage_servicios(user):
    # Igual permisos para servicios
    return has_role(user, ["Administrador", "Supervisor", "Asesor de Ventas"])


def can_manage_administracion(user):
    # Solo administradores y supervisores
    return has_role(user, ["Administrador", "Supervisor"])


def can_manage_whatsapp(user):
    return has_role(user, ["Administrador", "Supervisor", "Asesor de Ventas"])


def can_configure_whatsapp(user):
    return has_role(user, ["Administrador"])


# Decoradores para vistas

def leads_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not can_manage_leads(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def servicios_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not can_manage_servicios(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def campo_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not can_manage_campo(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def pizarra_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not can_manage_pizarra(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def conductor_helper_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not (can_driver_update_status(request.user) or can_view_assigned_services(request.user)):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def whatsapp_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not can_manage_whatsapp(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def whatsapp_config_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not can_configure_whatsapp(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view


