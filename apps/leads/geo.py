"""Clasificación local/nacional por distancia real (Fase "Direcciones", 2026-09).

Complementa —no reemplaza— la detección por texto que ya hace el bot de
WhatsApp (`apps.whatsapp.services_extraccion._menciona_ciudad_no_lima`, que
sigue intacta). Esta clasificación solo entra en juego cuando el lead tiene
coordenadas (lat/lng) capturadas por el autocompletado de direcciones en los
flujos web (invitado, portal cliente) — si no hay coordenadas, no hace nada.
"""
import math
from decimal import Decimal


def haversine_km(lat1, lng1, lat2, lng2):
    """Distancia en línea recta (km) entre dos puntos lat/lng."""
    lat1, lng1, lat2, lng2 = (float(v) for v in (lat1, lng1, lat2, lng2))
    r = 6371.0088  # radio medio de la Tierra, km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def clasificar_y_marcar_ambito(lead):
    """Si el lead tiene coordenadas de origen y/o destino, mide la distancia
    al punto de referencia local (`ConfiguracionOperaciones`) y actualiza
    `lead.es_interprovincial` en consecuencia. Guarda solo ese campo si cambió.
    No hace nada si no hay coordenadas (deja la detección por texto tal cual)."""
    from apps.servicios.models import ConfiguracionOperaciones

    puntos = [
        (lead.lat_origen, lead.lng_origen),
        (lead.lat_destino, lead.lng_destino),
    ]
    puntos = [(lat, lng) for lat, lng in puntos if lat is not None and lng is not None]
    if not puntos:
        return False

    config = ConfiguracionOperaciones.get_solo()
    ref_lat, ref_lng = config.lat_referencia_local, config.lng_referencia_local
    radio = Decimal(str(config.radio_local_km))
    es_nacional = any(
        Decimal(str(haversine_km(lat, lng, ref_lat, ref_lng))) > radio
        for lat, lng in puntos
    )
    if bool(lead.es_interprovincial) != es_nacional:
        lead.es_interprovincial = es_nacional
        lead.save(update_fields=["es_interprovincial"])
        return True
    return False
