from dataclasses import asdict, dataclass

from django.core.exceptions import ValidationError
from django.db import models, transaction

from .models import LeadUbicacion


@dataclass(frozen=True)
class LocationData:
    tipo: str
    distrito: str = ""
    direccion: str = ""
    piso: int | None = None
    ascensor: bool | None = None
    acceso_camion: bool | None = None
    distancia_acarreo: int | None = None
    observaciones_acceso: str = ""


def route_for_lead(lead, ensure_legacy=True):
    if not lead.pk:
        return _legacy_route(lead)
    locations = list(lead.ubicaciones.order_by("orden", "id"))
    if locations:
        return locations
    if not ensure_legacy:
        return _legacy_route(lead)
    return ensure_locations_from_legacy(lead)


@transaction.atomic
def ensure_locations_from_legacy(lead):
    locked = type(lead).objects.select_for_update().get(pk=lead.pk)
    existing = list(locked.ubicaciones.order_by("orden", "id"))
    if existing:
        return existing
    rows = _legacy_route(locked)
    if rows:
        LeadUbicacion.objects.bulk_create(
            [LeadUbicacion(lead=locked, orden=index, **asdict(row)) for index, row in enumerate(rows)]
        )
    return list(locked.ubicaciones.order_by("orden", "id"))


@transaction.atomic
def replace_lead_route(lead, locations):
    normalized = [_coerce_location(item) for item in locations]
    _validate_route(normalized)
    locked = type(lead).objects.select_for_update().get(pk=lead.pk)
    locked.ubicaciones.all().delete()
    created = LeadUbicacion.objects.bulk_create(
        [
            LeadUbicacion(lead=locked, orden=index, **asdict(location))
            for index, location in enumerate(normalized)
        ]
    )
    _sync_legacy_route(locked, created)
    return created


@transaction.atomic
def sync_legacy_endpoints(lead, changed_fields=()):
    route = route_for_lead(lead)
    by_type = {item.tipo: item for item in route}
    changed = set(changed_fields)
    endpoint_fields = {
        LeadUbicacion.ORIGEN: {
            "distrito": "distrito_origen", "direccion": "direccion_origen",
            "piso": "piso_origen", "ascensor": "ascensor_origen",
            "acceso_camion": "camion_llega_origen",
            "distancia_acarreo": "distancia_carga_origen_m",
            "observaciones_acceso": "acceso_origen",
        },
        LeadUbicacion.DESTINO: {
            "distrito": "distrito_destino", "direccion": "direccion_destino",
            "piso": "piso_destino", "ascensor": "ascensor_destino",
            "acceso_camion": "camion_llega_destino",
            "distancia_acarreo": "distancia_carga_destino_m",
            "observaciones_acceso": "acceso_destino",
        },
    }
    for location_type, mapping in endpoint_fields.items():
        updates = {
            target: getattr(lead, source)
            for target, source in mapping.items()
            if source in changed
        }
        if not updates:
            continue
        location = by_type.get(location_type)
        if location:
            for name, value in updates.items():
                setattr(location, name, value)
            location.save(update_fields=list(updates))
        else:
            max_order = max((item.orden for item in route), default=-1)
            order = 0 if location_type == LeadUbicacion.ORIGEN else max_order + 1
            if location_type == LeadUbicacion.ORIGEN:
                LeadUbicacion.objects.filter(lead=lead).update(orden=models.F("orden") + 1000)
                for index, item in enumerate(lead.ubicaciones.order_by("orden", "id"), start=1):
                    item.orden = index
                    item.save(update_fields=["orden"])
            location = LeadUbicacion.objects.create(
                lead=lead, orden=order, tipo=location_type, **updates
            )
            route.append(location)


@transaction.atomic
def remove_stop(lead, district):
    canonical = district.strip().lower()
    stops = list(
        lead.ubicaciones.select_for_update().filter(tipo=LeadUbicacion.PARADA).order_by("orden")
    )
    matches = [item for item in stops if item.distrito.strip().lower() == canonical]
    if len(matches) != 1:
        return False
    matches[0].delete()
    for order, location in enumerate(lead.ubicaciones.order_by("orden", "id")):
        if location.orden != order:
            location.orden = order
            location.save(update_fields=["orden"])
    return True


def route_summary(lead):
    return " → ".join(location.distrito or "?" for location in route_for_lead(lead))


def access_summary(lead):
    parts = []
    for location in route_for_lead(lead):
        values = []
        if location.piso is not None:
            values.append(f"piso {location.piso}")
        if location.ascensor is not None:
            values.append("con ascensor" if location.ascensor else "sin ascensor")
        if location.acceso_camion is not None:
            values.append("camión en puerta" if location.acceso_camion else "camión sin acceso directo")
        if location.distancia_acarreo is not None:
            values.append(f"acarreo {location.distancia_acarreo} m")
        if values:
            label = dict(LeadUbicacion.TIPOS).get(location.tipo, location.tipo)
            parts.append(f"{label} {location.distrito}: {', '.join(values)}")
    return " | ".join(parts)


def _coerce_location(item):
    if isinstance(item, LocationData):
        return item
    allowed = set(LocationData.__dataclass_fields__)
    return LocationData(**{key: value for key, value in item.items() if key in allowed})


def _validate_route(locations):
    if len(locations) < 2:
        raise ValidationError("La ruta requiere origen y destino.")
    if locations[0].tipo != LeadUbicacion.ORIGEN:
        raise ValidationError("La primera ubicación debe ser el origen.")
    if locations[-1].tipo != LeadUbicacion.DESTINO:
        raise ValidationError("La última ubicación debe ser el destino.")
    if sum(item.tipo == LeadUbicacion.ORIGEN for item in locations) != 1:
        raise ValidationError("La ruta requiere un único origen.")
    if sum(item.tipo == LeadUbicacion.DESTINO for item in locations) != 1:
        raise ValidationError("La ruta requiere un único destino.")
    if any(item.tipo not in dict(LeadUbicacion.TIPOS) for item in locations):
        raise ValidationError("Tipo de ubicación inválido.")
    if any(item.tipo == LeadUbicacion.PARADA for item in (locations[0], locations[-1])):
        raise ValidationError("Las paradas deben estar entre origen y destino.")


def _legacy_route(lead):
    rows = []
    if any(
        value not in (None, "")
        for value in (lead.distrito_origen, lead.direccion_origen, lead.piso_origen)
    ):
        rows.append(
            LocationData(
                tipo=LeadUbicacion.ORIGEN,
                distrito=lead.distrito_origen,
                direccion=lead.direccion_origen,
                piso=lead.piso_origen,
                ascensor=lead.ascensor_origen,
                acceso_camion=lead.camion_llega_origen,
                distancia_acarreo=lead.distancia_carga_origen_m,
                observaciones_acceso=lead.acceso_origen,
            )
        )
    if any(
        value not in (None, "")
        for value in (lead.distrito_destino, lead.direccion_destino, lead.piso_destino)
    ):
        rows.append(
            LocationData(
                tipo=LeadUbicacion.DESTINO,
                distrito=lead.distrito_destino,
                direccion=lead.direccion_destino,
                piso=lead.piso_destino,
                ascensor=lead.ascensor_destino,
                acceso_camion=lead.camion_llega_destino,
                distancia_acarreo=lead.distancia_carga_destino_m,
                observaciones_acceso=lead.acceso_destino,
            )
        )
    return rows


def _sync_legacy_route(lead, locations):
    origin = next(item for item in locations if item.tipo == LeadUbicacion.ORIGEN)
    destination = next(item for item in locations if item.tipo == LeadUbicacion.DESTINO)
    mapping = {
        "distrito_origen": origin.distrito,
        "direccion_origen": origin.direccion,
        "piso_origen": origin.piso,
        "ascensor_origen": origin.ascensor,
        "camion_llega_origen": origin.acceso_camion,
        "distancia_carga_origen_m": origin.distancia_acarreo,
        "acceso_origen": origin.observaciones_acceso,
        "distrito_destino": destination.distrito,
        "direccion_destino": destination.direccion,
        "piso_destino": destination.piso,
        "ascensor_destino": destination.ascensor,
        "camion_llega_destino": destination.acceso_camion,
        "distancia_carga_destino_m": destination.distancia_acarreo,
        "acceso_destino": destination.observaciones_acceso,
    }
    type(lead).objects.filter(pk=lead.pk).update(**mapping)
    for field_name, value in mapping.items():
        setattr(lead, field_name, value)
