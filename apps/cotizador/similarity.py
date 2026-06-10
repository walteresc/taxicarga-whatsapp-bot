from django.utils import timezone


def score_service(lead, service):
    score = 0
    if _same(lead.tipo_servicio, service.tipo_servicio):
        score += 4
    if _same(lead.distrito_origen, service.distrito_origen):
        score += 3
    if _same(lead.distrito_destino, service.distrito_destino):
        score += 3
    if lead.piso_origen is not None and lead.piso_origen == service.piso_origen:
        score += 1
    if lead.piso_destino is not None and lead.piso_destino == service.piso_destino:
        score += 1
    if lead.ascensor_origen is not None and lead.ascensor_origen == service.ascensor_origen:
        score += 1
    if lead.ascensor_destino is not None and lead.ascensor_destino == service.ascensor_destino:
        score += 1
    if _same(lead.modalidad_servicio, service.modalidad_servicio):
        score += 2
    if lead.incluye_personal_carga is not None:
        historical_has_personnel = service.ayudantes > 0
        if lead.incluye_personal_carga == historical_has_personnel:
            score += 2
    if (
        lead.requiere_desarmado is not None
        and lead.requiere_desarmado == service.requiere_desarmado
    ):
        score += 1
    if (
        lead.camion_llega_origen is not None
        and lead.camion_llega_origen == service.camion_llega_origen
    ):
        score += 1
    if (
        lead.camion_llega_destino is not None
        and lead.camion_llega_destino == service.camion_llega_destino
    ):
        score += 1
    if _close_number(lead.peso_carga_kg, service.peso_carga_kg, tolerance=250):
        score += 2
    if _close_number(lead.volumen_carga_m3, service.volumen_carga_m3, tolerance=3):
        score += 2
    score += _object_overlap(lead.lista_objetos, service.lista_objetos)
    score += _object_overlap(lead.objetos_pesados, service.objetos_pesados)
    weight = _recency_weight(service.fecha)
    return round(score * weight, 2)


def _same(left, right):
    return bool(left and right and _canonical(left) == _canonical(right))


def _object_overlap(left, right):
    left_words = set((left or "").lower().replace(",", " ").split())
    right_words = set((right or "").lower().replace(",", " ").split())
    return min(len(left_words & right_words), 3)


def _close_number(left, right, tolerance):
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance


def _canonical(value):
    normalized = " ".join(str(value).strip().lower().split())
    aliases = {
        "santiago de surco": "surco",
        "cercado de lima": "lima",
        "lima cercado": "lima",
        "magdalena del mar": "magdalena",
        "embalaje basico y traslado": "embalaje basico",
        "embalaje completo y traslado": "embalaje de muebles y artefactos",
        "solo traslado": "sin embalaje",
    }
    return aliases.get(normalized, normalized)


def _recency_weight(fecha):
    if not fecha:
        return 1.0
    delta = (timezone.localdate() - fecha).days
    if delta <= 90:
        return 1.0
    if delta <= 180:
        return 0.9
    if delta <= 365:
        return 0.75
    if delta <= 730:
        return 0.5
    return 0.25
