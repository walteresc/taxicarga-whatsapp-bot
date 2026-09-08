"""Única fuente de verdad EN↔ES de la API de Planilla."""

# clave API (canónica, camelCase)  ->  campo del modelo (BD, español)
CONFIG_FIELDS = {
    "workerType": "tipo",
    "workdayHours": "horas_jornada",
    "lunchHours": "horas_refrigerio",
    "contractType": "tipo_contrato",
    "amountPerDay": "monto_dia",
    "amountPerMonth": "monto_mes",
    "afpPct": "pct_afp",
    "hiredOn": "fecha_ingreso",
    "active": "activo",
    "notes": "observaciones",
}


def _invert(mapping):
    return {v: k for k, v in mapping.items()}


def api_to_model(mapping, data):
    return {mapping[k]: v for k, v in data.items() if k in mapping}


def model_to_api(mapping, data):
    inv = _invert(mapping)
    return {inv[k]: v for k, v in data.items() if k in inv}
