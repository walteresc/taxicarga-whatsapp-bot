"""Consultas y helpers del módulo Planilla."""
from django.db.models import Q

from apps.api.filters import apply_active_filter, apply_ordering
from apps.planilla.models import ConfiguracionPlanilla

_CONFIG_ORDER = {
    "hiredOn": "fecha_ingreso",
    "contractType": "tipo_contrato",
    "createdAt": "creado_en",
}


def configs_queryset(params):
    qs = ConfiguracionPlanilla.objects.select_related("conductor", "ayudante", "usuario")

    tipo = (params.get("workerType") or params.get("type") or "").strip()
    if tipo:
        qs = qs.filter(tipo=tipo)

    worker_id = params.get("workerId")
    if worker_id:
        qs = qs.filter(
            Q(tipo="conductor", conductor_id=worker_id)
            | Q(tipo="ayudante", ayudante_id=worker_id)
            | Q(tipo="asesor", usuario_id=worker_id)
        )

    contrato = (params.get("contractType") or "").strip()
    if contrato:
        qs = qs.filter(tipo_contrato=contrato)

    qs = apply_active_filter(qs, params.get("status"))

    term = (params.get("search") or "").strip()
    if term:
        qs = qs.filter(
            Q(conductor__nombre__icontains=term)
            | Q(ayudante__nombre__icontains=term)
            | Q(usuario__first_name__icontains=term)
            | Q(usuario__last_name__icontains=term)
            | Q(usuario__username__icontains=term)
            | Q(conductor__dni__icontains=term)
            | Q(ayudante__dni__icontains=term)
        )

    return apply_ordering(qs, params.get("ordering"), _CONFIG_ORDER, ("fecha_ingreso", "id"))
