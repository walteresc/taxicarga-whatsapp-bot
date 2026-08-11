import hashlib
import json
from dataclasses import dataclass

from apps.leads.route import route_for_lead

from .conversation_policy import effective_quote_values
from .delta_contract import SCHEMA_VERSION


@dataclass(frozen=True)
class CanonicalSnapshot:
    state_version: str
    state: dict


def build_canonical_snapshot(lead) -> CanonicalSnapshot:
    route = route_for_lead(lead, ensure_legacy=False)
    locations = {}
    for index, location in enumerate(route):
        if location.tipo == "origen":
            ref = "origin"
        elif location.tipo == "destino":
            ref = "destination"
        else:
            ref = f"order:{getattr(location, 'orden', index)}"
        locations[ref] = {
            "district": location.distrito or None,
            "floor": location.piso,
            "elevator": location.ascensor,
            "truck_access": location.acceso_camion,
            "carry_distance_m": location.distancia_acarreo,
            "access_observation": location.observaciones_acceso or None,
        }
    defaults = effective_quote_values(lead)
    state = {
        "schema_version": SCHEMA_VERSION,
        "service": lead.tipo_servicio or None,
        "service_date": lead.fecha_servicio.isoformat() if lead.fecha_servicio else None,
        "locations": locations,
        "load": lead.lista_objetos or None,
        "staff": {"required": defaults["incluye_personal_carga"]},
        "additional_services": {
            "packing": defaults["modalidad_servicio"] or None,
            "disassembly_required": defaults["requiere_desarmado"],
            "assembly_required": defaults["requiere_armado"],
        },
    }
    encoded = json.dumps(state, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return CanonicalSnapshot(
        state_version=hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24],
        state=state,
    )
