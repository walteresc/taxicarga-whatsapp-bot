from decimal import Decimal


BASE_PRICES = {
    "mudanza": Decimal("150.00"),
    "carga": Decimal("180.00"),
    "traslado pequeno": Decimal("150.00"),
    "oficina": Decimal("350.00"),
    "corporativo": Decimal("500.00"),
}


def fallback_price_for_lead(lead):
    base = BASE_PRICES.get((lead.tipo_servicio or "").lower(), Decimal("220.00"))
    price = base

    price += _floor_cost(lead.piso_origen, lead.ascensor_origen)
    price += _floor_cost(lead.piso_destino, lead.ascensor_destino)
    price += _volume_cost(lead.lista_objetos)
    price += _distance_cost(lead.distrito_origen, lead.distrito_destino)
    price += Decimal("50.00") if lead.incluye_personal_carga else Decimal("0.00")
    price += _packing_cost(lead.modalidad_servicio)
    price += _heavy_item_cost(lead.objetos_pesados)
    price += Decimal("90.00") if lead.requiere_desarmado else Decimal("0.00")
    price += _walking_cost(lead.distancia_carga_origen_m)
    price += _walking_cost(lead.distancia_carga_destino_m)
    price += Decimal("40.00") if lead.camion_llega_origen is False else Decimal("0.00")
    price += Decimal("40.00") if lead.camion_llega_destino is False else Decimal("0.00")
    price += _cargo_cost(lead.peso_carga_kg, lead.volumen_carga_m3)

    minimum = price * Decimal("0.90")
    maximum = price * Decimal("1.20")
    return minimum.quantize(Decimal("0.01")), maximum.quantize(Decimal("0.01")), price.quantize(Decimal("0.01"))


def _floor_cost(floor, has_elevator):
    if not floor or floor <= 1 or has_elevator:
        return Decimal("0.00")
    return Decimal(floor) * Decimal("35.00")


def _volume_cost(objects):
    words = (objects or "").split()
    if len(words) > 35:
        return Decimal("160.00")
    if len(words) > 15:
        return Decimal("90.00")
    if len(words) > 10:
        return Decimal("40.00")
    return Decimal("0.00")


def _distance_cost(origin, destination):
    return Decimal("0.00")


def _packing_cost(modality):
    normalized = (modality or "").lower()
    if "full" in normalized:
        return Decimal("350.00")
    if "muebles y artefactos" in normalized or "completo" in normalized:
        return Decimal("200.00")
    if "basico" in normalized or "básico" in normalized:
        return Decimal("150.00")
    return Decimal("0.00")


def _heavy_item_cost(items):
    count = len([item for item in (items or "").split(",") if item.strip()])
    return Decimal(count) * Decimal("45.00")


def _walking_cost(distance_m):
    if not distance_m or distance_m <= 20:
        return Decimal("0.00")
    blocks = Decimal(distance_m - 20) / Decimal("25")
    return blocks.to_integral_value(rounding="ROUND_CEILING") * Decimal("20.00")


def _cargo_cost(weight_kg, volume_m3):
    cost = Decimal("0.00")
    if weight_kg:
        cost += Decimal(weight_kg) * Decimal("0.12")
    if volume_m3:
        cost += Decimal(volume_m3) * Decimal("35.00")
    return cost
