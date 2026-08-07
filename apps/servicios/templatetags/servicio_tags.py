from django import template

from apps.servicios.models import (
    SERVICIO_ASIGNADO,
    SERVICIO_CANCELADO,
    SERVICIO_EN_RUTA,
    SERVICIO_FINALIZADO,
    SERVICIO_PENDIENTE,
    SERVICIO_PROGRAMADO,
)

register = template.Library()


@register.filter
def estado_color(estado):
    colors = {
        SERVICIO_PENDIENTE: "warning",
        SERVICIO_PROGRAMADO: "info",
        SERVICIO_ASIGNADO: "primary",
        SERVICIO_EN_RUTA: "primary",
        SERVICIO_FINALIZADO: "success",
        SERVICIO_CANCELADO: "error",
    }
    return colors.get(estado, "grey")
