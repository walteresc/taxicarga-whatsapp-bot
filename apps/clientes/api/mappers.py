"""Única fuente de verdad EN↔ES del módulo Clientes."""

# clave API (canónica, camelCase)  ->  campo del modelo (BD, español)
CUSTOMER_FIELDS = {
    "name": "nombre",
    "phone": "telefono",
    "documentId": "documento",
    "email": "correo",
    "taxId": "ruc",
    "businessName": "razon_social",
    "active": "is_active",
}


def _invert(mapping):
    return {v: k for k, v in mapping.items()}


def api_to_model(mapping, data):
    return {mapping[k]: v for k, v in data.items() if k in mapping}


def model_to_api(mapping, data):
    inv = _invert(mapping)
    return {inv[k]: v for k, v in data.items() if k in inv}
