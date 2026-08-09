from dataclasses import dataclass, field
from typing import Any


QUOTE = "quote"
QUOTE_READY = "quote_ready"
HUMAN_QUOTE = "human_quote"
QUOTED = "quoted"
BOOKING = "booking"


@dataclass(frozen=True)
class ConversationDecision:
    phase: str
    goal: str
    known_data: dict[str, Any]
    missing_relevant_data: tuple[str, ...] = ()
    pricing_result: Any = None
    must_handoff: bool = False
    response_constraints: tuple[str, ...] = field(default_factory=tuple)


def effective_quote_values(lead):
    service = (lead.tipo_servicio or "").lower()
    return {
        "incluye_personal_carga": (
            lead.incluye_personal_carga
            if lead.incluye_personal_carga is not None
            else (True if service == "mudanza" else None)
        ),
        "modalidad_servicio": lead.modalidad_servicio or (
            "sin embalaje" if service == "mudanza" else ""
        ),
        "requiere_desarmado": (
            lead.requiere_desarmado
            if lead.requiere_desarmado is not None
            else (False if service == "mudanza" else None)
        ),
        # No persistent field yet. Policy default remains explicit here.
        "requiere_armado": False if service == "mudanza" else None,
    }


def apply_quote_defaults(lead):
    if (lead.tipo_servicio or "").lower() != "mudanza":
        return []
    changed = []
    defaults = {
        "incluye_personal_carga": True,
        "modalidad_servicio": "sin embalaje",
        "requiere_desarmado": False,
    }
    for field_name, value in defaults.items():
        if getattr(lead, field_name) in (None, ""):
            setattr(lead, field_name, value)
            changed.append(field_name)
    return changed


def quote_missing_fields(lead, requires_truck_access=False):
    missing = []
    if not lead.tipo_servicio:
        missing.append("tipo_servicio")
    if not lead.distrito_origen:
        missing.append("distrito_origen")
    if not lead.distrito_destino:
        missing.append("distrito_destino")
    if not lead.lista_objetos:
        missing.append("lista_objetos")

    service = (lead.tipo_servicio or "").lower()
    if service == "carga" and lead.peso_carga_kg is None and lead.volumen_carga_m3 is None:
        missing.append("dimension_carga")

    if lead.piso_origen is None:
        missing.append("piso_origen")
    elif lead.piso_origen > 1 and lead.ascensor_origen is None:
        missing.append("ascensor_origen")
    if lead.piso_destino is None:
        missing.append("piso_destino")
    elif lead.piso_destino > 1 and lead.ascensor_destino is None:
        missing.append("ascensor_destino")

    if requires_truck_access:
        if lead.camion_llega_origen is None:
            missing.append("camion_llega_origen")
        if lead.camion_llega_destino is None:
            missing.append("camion_llega_destino")
    return missing


def booking_missing_fields(lead):
    missing = []
    if not lead.cliente.nombre:
        missing.append("cliente_nombre")
    if not _specific_address(lead.direccion_origen):
        missing.append("direccion_origen")
    if not _specific_address(lead.direccion_destino):
        missing.append("direccion_destino")
    if not lead.fecha_servicio:
        missing.append("fecha_servicio")
    if not lead.horario_servicio:
        missing.append("horario_servicio")
    return missing


def decide_conversation(lead, requires_truck_access=False, must_handoff=False):
    known = _known_snapshot(lead)
    if must_handoff:
        return ConversationDecision(
            phase=HUMAN_QUOTE,
            goal="handoff_quote",
            known_data=known,
            must_handoff=True,
            response_constraints=("No calcular precio",),
        )
    if lead.etapa_conversacion == "reserva":
        missing = tuple(booking_missing_fields(lead))
        return ConversationDecision(
            phase=BOOKING,
            goal="collect_booking" if missing else "booking_ready",
            known_data=known,
            missing_relevant_data=missing,
            response_constraints=("DNI opcional", "No afirmar reserva creada"),
        )
    missing = tuple(quote_missing_fields(lead, requires_truck_access))
    return ConversationDecision(
        phase=QUOTE if missing else QUOTE_READY,
        goal=_goal_for(missing) if missing else "calculate_quote",
        known_data=known,
        missing_relevant_data=missing,
        response_constraints=("Breve", "No inventar precio", "No pedir datos administrativos"),
    )


def _goal_for(missing):
    fields = set(missing)
    if fields & {"tipo_servicio"}:
        return "collect_service"
    if fields & {"distrito_origen", "distrito_destino"}:
        return "collect_route"
    if fields & {"lista_objetos", "dimension_carga"}:
        return "collect_load"
    if fields & {
        "piso_origen", "piso_destino", "ascensor_origen", "ascensor_destino",
        "camion_llega_origen", "camion_llega_destino",
    }:
        return "collect_access"
    return "collect_quote"


def _known_snapshot(lead):
    names = (
        "tipo_servicio", "distrito_origen", "distrito_destino", "lista_objetos",
        "piso_origen", "piso_destino", "ascensor_origen", "ascensor_destino",
        "incluye_personal_carga", "modalidad_servicio", "requiere_desarmado",
        "fecha_servicio", "horario_servicio", "direccion_origen", "direccion_destino",
    )
    return {name: getattr(lead, name) for name in names if getattr(lead, name) not in (None, "")}


def _specific_address(value):
    if not value:
        return False
    lowered = value.lower()
    has_number = any(char.isdigit() for char in value)
    has_location = any(
        token in lowered for token in ("avenida", "av.", "calle", "jirón", "jiron", "jr.", "manzana", "mz.")
    )
    return has_number and has_location
