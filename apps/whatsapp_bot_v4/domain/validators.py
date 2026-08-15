from .state import Access, BotState


STATE_FIELDS = frozenset(BotState.__dataclass_fields__)


class DomainValidationError(ValueError):
    pass


def validate_value(field: str, value):
    if field not in STATE_FIELDS:
        raise DomainValidationError(f"Campo no permitido: {field}")
    if value is None:
        return None
    if field.endswith("_district"):
        if not isinstance(value, str) or not value.strip():
            raise DomainValidationError(f"{field} debe ser texto no vacío")
        return value.strip()
    if field.endswith("_floor"):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 100:
            raise DomainValidationError(f"{field} debe ser entero entre 1 y 100")
        return value
    if field.endswith("_access"):
        try:
            return Access(value)
        except (TypeError, ValueError) as exc:
            raise DomainValidationError(f"Acceso inválido para {field}: {value}") from exc
    if field == "items":
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            raise DomainValidationError("items debe ser lista de textos no vacíos")
        return [item.strip() for item in value]
    if field == "request_boundary_at":
        # ISO timestamp or None
        if not isinstance(value, str):
            raise DomainValidationError(f"{field} debe ser ISO timestamp string")
        return value
    raise DomainValidationError(f"Campo sin validador: {field}")


def validate_state(state: BotState) -> None:
    for field in STATE_FIELDS:
        validate_value(field, getattr(state, field))
    if state.origin_floor == 1 and state.origin_access != Access.NOT_APPLICABLE:
        raise DomainValidationError("origin_access debe ser NOT_APPLICABLE en piso 1")
    if state.destination_floor == 1 and state.destination_access != Access.NOT_APPLICABLE:
        raise DomainValidationError("destination_access debe ser NOT_APPLICABLE en piso 1")
    if state.origin_floor and state.origin_floor > 1 and state.origin_access == Access.NOT_APPLICABLE:
        raise DomainValidationError("origin_access no puede ser NOT_APPLICABLE sobre piso 1")
    if state.destination_floor and state.destination_floor > 1 and state.destination_access == Access.NOT_APPLICABLE:
        raise DomainValidationError("destination_access no puede ser NOT_APPLICABLE sobre piso 1")
