from dataclasses import dataclass, field
import re
from typing import Any

from apps.leads.route import route_for_lead


QUOTE = "quote"
QUOTE_READY = "quote_ready"
HUMAN_QUOTE = "human_quote"
QUOTED = "quoted"
BOOKING = "booking"


@dataclass(frozen=True)
class QuestionTarget:
    field: str
    ref: str | None = None
    operation: str = "set"

    def as_dict(self):
        return {"field": self.field, "ref": self.ref, "operation": self.operation}


@dataclass(frozen=True)
class ConversationDecision:
    phase: str
    goal: str
    known_data: dict[str, Any]
    missing_relevant_data: tuple[str, ...] = ()
    pricing_result: Any = None
    must_handoff: bool = False
    response_constraints: tuple[str, ...] = field(default_factory=tuple)
    question_targets: tuple[QuestionTarget, ...] = field(default_factory=tuple)


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
        "requiere_armado": (
            lead.requiere_armado
            if lead.requiere_armado is not None
            else (False if service == "mudanza" else None)
        ),
    }


def apply_quote_defaults(lead):
    if (lead.tipo_servicio or "").lower() != "mudanza":
        return []
    changed = []
    defaults = {
        "incluye_personal_carga": True,
        "modalidad_servicio": "sin embalaje",
        "requiere_desarmado": False,
        "requiere_armado": False,
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
    route = route_for_lead(lead, ensure_legacy=False)
    if not route:
        missing.extend(["distrito_origen", "distrito_destino"])
    else:
        route_types = {location.tipo for location in route}
        if "origen" not in route_types:
            missing.append("distrito_origen")
        if "destino" not in route_types:
            missing.append("distrito_destino")
        for order, location in enumerate(route):
            if not location.distrito:
                missing.append(f"ubicacion_{getattr(location, 'orden', order)}_distrito")
    if not lead.lista_objetos:
        missing.append("lista_objetos")

    service = (lead.tipo_servicio or "").lower()
    if service == "carga" and lead.peso_carga_kg is None and lead.volumen_carga_m3 is None:
        missing.append("dimension_carga")

    for order, location in enumerate(route):
        location_order = getattr(location, "orden", order)
        if location.piso is None:
            missing.append(f"ubicacion_{location_order}_piso")
        elif location.piso > 1 and location.ascensor is None:
            missing.append(f"ubicacion_{location_order}_ascensor")

    if requires_truck_access:
        for order, location in enumerate(route):
            if location.acceso_camion is None:
                missing.append(f"ubicacion_{getattr(location, 'orden', order)}_acceso_camion")
    return missing


def booking_missing_fields(lead):
    missing = []
    if not lead.cliente.nombre:
        missing.append("cliente_nombre")
    route = route_for_lead(lead, ensure_legacy=False)
    if not route:
        missing.extend(["direccion_origen", "direccion_destino"])
    else:
        route_types = {location.tipo for location in route}
        if "origen" not in route_types:
            missing.append("direccion_origen")
        if "destino" not in route_types:
            missing.append("direccion_destino")
        for order, location in enumerate(route):
            if not _specific_address(location.direccion):
                missing.append(f"ubicacion_{getattr(location, 'orden', order)}_direccion")
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
        question_targets=_question_targets(missing),
    )


def _question_targets(missing):
    targets = []
    direct = {
        "tipo_servicio": ("service", None), "lista_objetos": ("load", None),
        "dimension_carga": ("load", None),
        "distrito_origen": ("district", "origin"),
        "distrito_destino": ("district", "destination"),
        "piso_origen": ("floor", "origin"), "piso_destino": ("floor", "destination"),
        "ascensor_origen": ("elevator", "origin"),
        "ascensor_destino": ("elevator", "destination"),
        "camion_llega_origen": ("access_observation", "origin"),
        "camion_llega_destino": ("access_observation", "destination"),
    }
    for name in missing:
        mapped = direct.get(name)
        if mapped:
            targets.append(QuestionTarget(*mapped))
            continue
        match = re.match(r"ubicacion_(\d+)_(distrito|piso|ascensor|acceso_camion)$", name)
        if match:
            order, field_name = match.groups()
            field_name = "access_observation" if field_name == "acceso_camion" else field_name
            targets.append(QuestionTarget(field_name, f"location:{order}"))
    return tuple(targets)


def question_targets_for_decision(decision):
    return [target.as_dict() for target in decision.question_targets]


def _goal_for(missing):
    fields = set(missing)
    if fields & {"tipo_servicio"}:
        return "collect_service"
    if fields & {"distrito_origen", "distrito_destino"} or any(field.endswith("_distrito") for field in fields):
        return "collect_route"
    if fields & {"lista_objetos", "dimension_carga"}:
        return "collect_load"
    if fields & {
        "piso_origen", "piso_destino", "ascensor_origen", "ascensor_destino",
        "camion_llega_origen", "camion_llega_destino",
    } or any(field.endswith(("_piso", "_ascensor", "_acceso_camion")) for field in fields):
        return "collect_access"
    return "collect_quote"


def _known_snapshot(lead):
    names = (
        "tipo_servicio", "distrito_origen", "distrito_destino", "lista_objetos",
        "piso_origen", "piso_destino", "ascensor_origen", "ascensor_destino",
        "incluye_personal_carga", "modalidad_servicio", "requiere_desarmado",
        "fecha_servicio", "horario_servicio", "direccion_origen", "direccion_destino",
    )
    snapshot = {name: getattr(lead, name) for name in names if getattr(lead, name) not in (None, "")}
    snapshot["ubicaciones"] = [
        {
            "orden": getattr(location, "orden", order),
            "tipo": location.tipo,
            "distrito": location.distrito,
            "direccion": location.direccion,
            "piso": location.piso,
            "ascensor": location.ascensor,
            "acceso_camion": location.acceso_camion,
        }
        for order, location in enumerate(route_for_lead(lead, ensure_legacy=False))
    ]
    return snapshot


def _specific_address(value):
    if not value:
        return False
    lowered = value.lower()
    has_number = any(char.isdigit() for char in value)
    has_location = any(
        token in lowered for token in ("avenida", "av.", "calle", "jirón", "jiron", "jr.", "manzana", "mz.")
    )
    return has_number and has_location
