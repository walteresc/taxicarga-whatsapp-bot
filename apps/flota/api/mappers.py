"""Única fuente de verdad EN↔ES del módulo Flota (vehículos y mantenimientos).

El modelo `Vehiculo` vive en `apps.campo` (no se mueve: cero beneficio, migración
grande). `apps.flota` es el dueño del dominio en el panel nuevo, así que su API
expone ambos recursos.
"""

# --- Vehículos ------------------------------------------------------------
# clave API (canónica, camelCase)  ->  campo del modelo (BD, español)
VEHICLE_FIELDS = {
    "plate": "placa",
    "brand": "marca",
    "model": "modelo",
    "year": "anio",
    "capacityTons": "capacidad_toneladas",
    "capacityM3": "capacidad_m3",
    "soatExpiresOn": "fecha_vencimiento_soat",
    "technicalReviewExpiresOn": "fecha_vencimiento_rtv",
    "fireExtinguisherExpiresOn": "fecha_vencimiento_extintor",
    "active": "activo",
    "notes": "observaciones",
}

# --- Mantenimientos -----------------------------------------------------
MAINTENANCE_FIELDS = {
    "vehicleId": "vehiculo",          # FK (por id en escritura)
    "performedOn": "fecha_mantenimiento",
    "odometer": "kilometraje_actual",
    "nextServiceOdometer": "proximo_mantenimiento_km",
    "work": "descripcion",
    "notes": "observaciones",
}


def _invert(mapping):
    return {v: k for k, v in mapping.items()}


def api_to_model(mapping, data):
    return {mapping[k]: v for k, v in data.items() if k in mapping}


def model_to_api(mapping, data):
    inv = _invert(mapping)
    return {inv[k]: v for k, v in data.items() if k in inv}
