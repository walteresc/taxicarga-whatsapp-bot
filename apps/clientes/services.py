"""Consulta de clientes. Compartida entre panel viejo y API v2."""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.api.filters import apply_active_filter, apply_ordering, apply_search
from apps.clientes.models import Cliente

_ORDERING = {
    "name": "nombre",
    "createdAt": "fecha_creacion",
    "lastInteraction": "ultima_interaccion",
}

# Un cliente sin interacción en este lapso se considera inactivo.
INACTIVO_DIAS = 180
# Servicios cerrados para considerar "frecuente".
FRECUENTE_MIN_SERVICIOS = 3


def _es_empresa_q():
    return ~Q(ruc="") | ~Q(razon_social="")


def segmento_cliente(cliente, *, n_servicios=None):
    """Clasifica un cliente: empresa / frecuente / ocasional / inactivo / nuevo."""
    if not cliente.is_active:
        return "inactivo"
    if (timezone.now() - cliente.ultima_interaccion) > timedelta(days=INACTIVO_DIAS):
        return "inactivo"
    if (cliente.ruc or cliente.razon_social):
        return "empresa"
    n = n_servicios if n_servicios is not None else cliente.servicios.count()
    if n >= FRECUENTE_MIN_SERVICIOS:
        return "frecuente"
    if n >= 1:
        return "ocasional"
    return "nuevo"


def customers_queryset(params):
    qs = Cliente.objects.annotate(n_servicios=Count("servicios", distinct=True))
    qs = apply_search(
        qs, params.get("search"),
        ("nombre", "display_name", "telefono", "documento", "correo", "razon_social"),
    )
    qs = apply_active_filter(qs, params.get("status"), field="is_active")

    segment = (params.get("segment") or "").strip().lower()
    cutoff = timezone.now() - timedelta(days=INACTIVO_DIAS)
    inactivo_q = Q(is_active=False) | Q(ultima_interaccion__lt=cutoff)
    if segment == "empresa":
        qs = qs.filter(_es_empresa_q()).exclude(inactivo_q)
    elif segment == "frecuente":
        qs = qs.filter(ruc="", razon_social="", n_servicios__gte=FRECUENTE_MIN_SERVICIOS).exclude(inactivo_q)
    elif segment == "ocasional":
        qs = qs.filter(
            ruc="", razon_social="", n_servicios__gte=1, n_servicios__lt=FRECUENTE_MIN_SERVICIOS,
        ).exclude(inactivo_q)
    elif segment == "inactivo":
        qs = qs.filter(inactivo_q)

    qs = apply_ordering(qs, params.get("ordering"), _ORDERING, ("-fecha_creacion", "-id"))
    return qs
