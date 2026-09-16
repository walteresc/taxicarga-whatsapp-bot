"""Clasificación local/nacional por distancia real (Fase "Direcciones", 2026-09).

Complementa —no reemplaza— la detección por texto que ya hace el bot de
WhatsApp (`apps.whatsapp.services_extraccion._menciona_ciudad_no_lima`, que
sigue intacta y a la que este módulo NO se conecta a propósito — es zona
frágil). La clasificación por distancia solo entra en juego cuando el lead
tiene coordenadas (autocompletado de direcciones en invitado/portal cliente).

Cuando NO hay coordenadas (dirección tipeada a mano, sin elegir sugerencia),
se usa un respaldo mucho más simple: una lista propia y acotada de ciudades
fuera de Lima (independiente de la del bot, para no acoplarse a esa zona
frágil). Es best-effort y **solo puede marcar `es_interprovincial=True`**,
nunca lo revierte a False — así no pisa una clasificación ya hecha por el
bot o por un asesor."""
import math
from decimal import Decimal

# Ciudades/regiones grandes del Perú fuera de Lima Metropolitana + Callao.
# Deliberadamente chica: es un respaldo cuando no hay geolocalización, no el
# mecanismo principal (ese es la distancia real, arriba).
_CIUDADES_NO_LIMA = {
    "arequipa", "cusco", "cuzco", "trujillo", "chiclayo", "piura", "iquitos",
    "tacna", "puno", "juliaca", "huancayo", "ica", "tumbes", "chimbote",
    "cajamarca", "pucallpa", "ayacucho", "huaraz", "moquegua", "abancay",
    "huanuco", "huánuco", "tarapoto", "moyobamba", "chachapoyas", "pasco",
    "cerro de pasco", "chincha", "cañete", "canete", "huaral", "barranca",
}


def _parece_fuera_de_lima(texto):
    palabras = {w.strip(".,") for w in (texto or "").lower().split()}
    return bool(palabras & _CIUDADES_NO_LIMA)


def haversine_km(lat1, lng1, lat2, lng2):
    """Distancia en línea recta (km) entre dos puntos lat/lng."""
    lat1, lng1, lat2, lng2 = (float(v) for v in (lat1, lng1, lat2, lng2))
    r = 6371.0088  # radio medio de la Tierra, km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def evaluar_ambito(lead):
    """Misma clasificación que `clasificar_y_marcar_ambito`, pero de solo
    lectura (no guarda nada) — para un lead sin persistir todavía, como el
    preview de precio del cotizador antes de publicar la solicitud."""
    from apps.servicios.models import ConfiguracionOperaciones

    puntos = [
        (lead.lat_origen, lead.lng_origen),
        (lead.lat_destino, lead.lng_destino),
    ]
    puntos = [(lat, lng) for lat, lng in puntos if lat is not None and lng is not None]
    if not puntos:
        return bool(lead.es_interprovincial) or _parece_fuera_de_lima(
            f"{lead.distrito_origen or ''} {lead.distrito_destino or ''}"
        )

    config = ConfiguracionOperaciones.get_solo()
    ref_lat, ref_lng = config.lat_referencia_local, config.lng_referencia_local
    radio = Decimal(str(config.radio_local_km))
    return any(
        Decimal(str(haversine_km(lat, lng, ref_lat, ref_lng))) > radio
        for lat, lng in puntos
    )


def clasificar_y_marcar_ambito(lead):
    """Si el lead tiene coordenadas de origen y/o destino, mide la distancia
    al punto de referencia local (`ConfiguracionOperaciones`) y actualiza
    `lead.es_interprovincial` en consecuencia. Guarda solo ese campo si cambió.
    No hace nada si no hay coordenadas (deja la detección por texto tal cual)."""
    nuevo = evaluar_ambito(lead)
    if bool(lead.es_interprovincial) != nuevo:
        lead.es_interprovincial = nuevo
        lead.save(update_fields=["es_interprovincial"])
        return True
    return False
