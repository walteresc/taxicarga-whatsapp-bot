"""Única fuente de verdad de la traducción inglés↔español del módulo Personal.

La API habla inglés canónico; el modelo (BD) está en español. Todo el mapeo
—campos y valores de enum— vive aquí. Ni el serializer ni el viewset ni el
frontend traducen nada por su cuenta.

    api_to_model(DRIVER_FIELDS, {"name": "Ana"})   -> {"nombre": "Ana"}
    model_to_api(DRIVER_FIELDS, {"nombre": "Ana"}) -> {"name": "Ana"}
"""

# --- Conductores ------------------------------------------------------------
# clave API (canónica, camelCase)  ->  campo del modelo (BD, español)
DRIVER_FIELDS = {
    "name": "nombre",
    "documentId": "dni",
    "phone": "telefono",
    "licenseNumber": "numero_licencia",
    "licenseCategory": "categoria_licencia",
    "licenseExpiresOn": "fecha_vencimiento_licencia",
    "active": "activo",
    "notes": "observaciones",
}

# --- Ayudantes -------------------------------------------------------------
ASSISTANT_FIELDS = {
    "name": "nombre",
    "documentId": "dni",
    "phone": "telefono",
    "active": "activo",
    "notes": "observaciones",
}

# Categoría de licencia: el valor es el mismo string en ambos lados (A-I, B-II-a…),
# así que el mapa es identidad. Se declara explícito para que añadir/renombrar una
# categoría sea un cambio en un solo sitio.
from apps.campo.models import Conductor  # noqa: E402

LICENSE_CATEGORY = {value: value for value, _label in Conductor.LICENCIA_CATEGORIAS}


# --- helpers de ida y vuelta ---------------------------------------------------

def _invert(mapping):
    return {v: k for k, v in mapping.items()}


def api_to_model(mapping, data):
    """Renombra claves API -> modelo. Ignora claves desconocidas."""
    return {mapping[k]: v for k, v in data.items() if k in mapping}


def model_to_api(mapping, data):
    """Renombra claves modelo -> API. Ignora claves desconocidas."""
    inv = _invert(mapping)
    return {inv[k]: v for k, v in data.items() if k in inv}
