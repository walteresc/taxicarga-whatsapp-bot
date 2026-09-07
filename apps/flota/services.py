"""Lógica de consulta y avisos del módulo Flota.

Separada de las vistas para compartirla entre el panel viejo (Django) y la API v2
(Vue). `vehicle_alerts()` es el aviso de vencimientos que pidió el usuario: hoy
esa información existe en los campos del vehículo pero nada la vigila.
"""
import datetime as dt

from django.db.models import Max
from django.utils import timezone

from apps.api.filters import apply_active_filter, apply_ordering, apply_search
from apps.campo.models import Vehiculo
from apps.flota.models import MantenimientoVehiculo

_VEHICLE_ORDERING = {
    "plate": "placa", "brand": "marca", "year": "anio", "active": "activo",
    "soatExpiresOn": "fecha_vencimiento_soat",
    "technicalReviewExpiresOn": "fecha_vencimiento_rtv",
}
_MAINT_ORDERING = {
    "performedOn": "fecha_mantenimiento", "odometer": "kilometraje_actual",
    "vehiclePlate": "vehiculo__placa",
}

# Umbrales del aviso.
DIAS_AVISO = 30           # documento que vence en <= 30 días -> "por vencer"
KM_AVISO = 1000           # faltan <= 1000 km para el próximo servicio -> "por vencer"


def vehicles_queryset(params):
    qs = Vehiculo.objects.all()
    qs = apply_search(qs, params.get("search"), ("placa", "marca", "modelo"))
    qs = apply_active_filter(qs, params.get("status"))
    qs = apply_ordering(qs, params.get("ordering"), _VEHICLE_ORDERING, ("placa", "id"))
    return qs


def maintenance_queryset(params):
    qs = MantenimientoVehiculo.objects.select_related("vehiculo")
    vehicle_id = params.get("vehicleId")
    if vehicle_id:
        qs = qs.filter(vehiculo_id=vehicle_id)
    qs = apply_search(qs, params.get("search"), ("vehiculo__placa", "descripcion", "observaciones"))
    qs = apply_ordering(qs, params.get("ordering"), _MAINT_ORDERING, ("-fecha_mantenimiento", "-id"))
    return qs


# --- Avisos de vencimientos -------------------------------------------------

def _date_status(value, today):
    if not value:
        return "unknown", None
    days = (value - today).days
    if days < 0:
        return "overdue", days
    if days <= DIAS_AVISO:
        return "due_soon", days
    return "ok", days


_SEVERITY = {"overdue": 0, "due_soon": 1, "unknown": 2, "ok": 3}


def vehicle_alerts():
    """Un item por vehículo activo que tiene al menos un aviso (documento vencido
    o por vencer, o servicio por kilometraje). Ordenado por severidad."""
    today = timezone.localdate()

    # Última lectura de odómetro y próximo servicio por vehículo (del histórico
    # de mantenimientos; no hay odómetro "en vivo" en el modelo de vehículo).
    ultimos = {}
    for m in (MantenimientoVehiculo.objects
              .order_by("vehiculo_id", "-fecha_mantenimiento", "-id")):
        ultimos.setdefault(m.vehiculo_id, m)

    items = []
    for v in Vehiculo.objects.filter(activo=True):
        avisos = []
        for etiqueta, campo in (
            ("SOAT", v.fecha_vencimiento_soat),
            ("Revisión técnica", v.fecha_vencimiento_rtv),
            ("Extintor", v.fecha_vencimiento_extintor),
        ):
            estado, dias = _date_status(campo, today)
            if estado in ("overdue", "due_soon"):
                avisos.append({
                    "type": "document", "label": etiqueta, "status": estado,
                    "date": campo.isoformat() if campo else None, "daysLeft": dias,
                })

        m = ultimos.get(v.id)
        if m and m.proximo_mantenimiento_km:
            restante = m.proximo_mantenimiento_km - (m.kilometraje_actual or 0)
            if restante <= 0:
                estado = "overdue"
            elif restante <= KM_AVISO:
                estado = "due_soon"
            else:
                estado = "ok"
            if estado != "ok":
                avisos.append({
                    "type": "service", "label": "Mantenimiento por kilometraje",
                    "status": estado, "nextServiceOdometer": m.proximo_mantenimiento_km,
                    "lastOdometerReading": m.kilometraje_actual, "remainingKm": restante,
                })

        if avisos:
            avisos.sort(key=lambda a: _SEVERITY[a["status"]])
            items.append({
                "vehicleId": v.id, "plate": v.placa,
                "vehicle": f"{v.placa} · {v.marca} {v.modelo}".strip(" ·"),
                "worstStatus": avisos[0]["status"], "alerts": avisos,
            })

    items.sort(key=lambda it: _SEVERITY[it["worstStatus"]])
    return items
