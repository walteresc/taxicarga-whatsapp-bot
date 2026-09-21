from decimal import Decimal

_BASE_FIELD_BY_TIPO = {
    "mudanza": "base_mudanza",
    "carga": "base_carga",
    "traslado pequeno": "base_traslado_pequeno",
    "oficina": "base_oficina",
    "corporativo": "base_corporativo",
}


def panel_prices(lead):
    """(sugerido, cotizado) para el panel derecho de la bandeja y el modal de
    Cotizar. Una sola definición para que ambos muestren exactamente el mismo
    número. `sugerido` sale del motor (fallback); `cotizado` es lo que ya se le
    envió al cliente, si existe."""
    if lead is None:
        return None, None
    quoted = lead.precio_cotizado or lead.precio_final or None
    try:
        suggested = fallback_price_for_lead(lead)[2]
    except Exception:
        suggested = lead.precio_recomendado or None
    return suggested, quoted


def fallback_price_for_lead(lead):
    from apps.cotizador.models import ConfiguracionPrecios

    config = ConfiguracionPrecios.get_solo()
    price = _base_price(lead.tipo_servicio, config)

    price += _floor_cost(lead.piso_origen, lead.ascensor_origen, config)
    price += _floor_cost(lead.piso_destino, lead.ascensor_destino, config)
    price += _volume_cost(lead.lista_objetos, config)
    if not getattr(lead, "es_interprovincial", False):
        price += _distance_cost(lead.lat_origen, lead.lng_origen, lead.lat_destino, lead.lng_destino, config)
    price += config.costo_personal_carga if lead.incluye_personal_carga else Decimal("0.00")
    price += _packing_cost(lead.modalidad_servicio, config)
    price += _heavy_item_cost(lead.objetos_pesados, config)
    price += config.costo_desarmado if lead.requiere_desarmado else Decimal("0.00")
    price += _walking_cost(lead.distancia_carga_origen_m, config)
    price += _walking_cost(lead.distancia_carga_destino_m, config)
    price += config.costo_camion_no_llega if lead.camion_llega_origen is False else Decimal("0.00")
    price += config.costo_camion_no_llega if lead.camion_llega_destino is False else Decimal("0.00")
    price += _cargo_cost(lead.peso_carga_kg, lead.volumen_carga_m3, config)

    minimum = price * (config.rango_min_pct / Decimal("100"))
    maximum = price * (config.rango_max_pct / Decimal("100"))
    return minimum.quantize(Decimal("0.01")), maximum.quantize(Decimal("0.01")), price.quantize(Decimal("0.01"))


def _base_price(tipo_servicio, config):
    field = _BASE_FIELD_BY_TIPO.get((tipo_servicio or "").lower())
    return getattr(config, field) if field else config.base_otros


def _floor_cost(floor, has_elevator, config):
    if not floor or floor <= 1 or has_elevator:
        return Decimal("0.00")
    return Decimal(floor) * config.costo_por_piso_sin_ascensor


def _volume_cost(objects, config):
    words = (objects or "").split()
    if len(words) > 35:
        return config.costo_descripcion_muy_grande
    if len(words) > 15:
        return config.costo_descripcion_grande
    if len(words) > 10:
        return config.costo_descripcion_media
    return Decimal("0.00")


def _distance_cost(lat_origen, lng_origen, lat_destino, lng_destino, config):
    """Línea recta origen-destino (haversine, igual que apps/leads/geo.py) —
    0 si al Lead le falta alguna coordenada (leads de WhatsApp o cargados a
    mano sin geocodificar; en /cotizar y Portal Cliente el autocompletado de
    distrito ya obliga a elegir una sugerencia con coordenadas).

    Solo se llama para rutas LOCALES (ver fallback_price_for_lead) — una
    tarifa lineal por km no tiene sentido para carga nacional (Lima-Arequipa
    son ~900km: a S/2.50/km serían +S/2250 por una sola cama). Carga
    nacional se cotiza aparte, por destino/peso (TarifaCargaParcial) o
    siempre a un asesor."""
    if None in (lat_origen, lng_origen, lat_destino, lng_destino):
        return Decimal("0.00")
    from apps.leads.geo import haversine_km

    km = Decimal(str(haversine_km(lat_origen, lng_origen, lat_destino, lng_destino)))
    km_cobrables = km - config.km_gratis
    if km_cobrables <= 0:
        return Decimal("0.00")
    return km_cobrables * config.costo_por_km


def _packing_cost(modality, config):
    normalized = (modality or "").lower()
    if "full" in normalized:
        return config.costo_embalaje_full
    if "muebles y artefactos" in normalized or "completo" in normalized:
        return config.costo_embalaje_completo
    if "basico" in normalized or "básico" in normalized:
        return config.costo_embalaje_basico
    return Decimal("0.00")


def _heavy_item_cost(items, config):
    count = len([item for item in (items or "").split(",") if item.strip()])
    return Decimal(count) * config.costo_objeto_pesado


def _walking_cost(distance_m, config):
    if not distance_m or distance_m <= 20:
        return Decimal("0.00")
    blocks = Decimal(distance_m - 20) / Decimal("25")
    return blocks.to_integral_value(rounding="ROUND_CEILING") * config.costo_caminata_por_bloque


def _cargo_cost(weight_kg, volume_m3, config):
    cost = Decimal("0.00")
    if weight_kg:
        cost += Decimal(weight_kg) * config.costo_por_kg
    if volume_m3:
        cost += Decimal(volume_m3) * config.costo_por_m3
    return cost
