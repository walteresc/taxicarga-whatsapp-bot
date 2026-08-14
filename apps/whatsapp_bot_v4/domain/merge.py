import logging

from .state import Access, BotState
from .validators import DomainValidationError, validate_state, validate_value


logger = logging.getLogger(__name__)


def merge_state(state: BotState, updates: dict, corrections: dict) -> BotState:
    overlap = set(updates) & set(corrections)
    if overlap:
        raise DomainValidationError(f"Campos duplicados en updates/corrections: {sorted(overlap)}")
    merged = state.copy()
    for field, raw_value in updates.items():
        if raw_value is None:
            continue
        value = validate_value(field, raw_value)
        current = getattr(merged, field)
        if current not in (None, [], "") and current != value:
            logger.warning(
                "bot_v4_merge_conflict field=%s current=%r value=%r updates=%r",
                field, current, value, updates,
            )
            raise DomainValidationError(f"{field} requiere corrección explícita para sobrescribir")
        setattr(merged, field, value)
    for field, raw_value in corrections.items():
        if raw_value is None:
            raise DomainValidationError(f"Corrección nula no permitida: {field}")
        setattr(merged, field, validate_value(field, raw_value))
    for prefix in ("origin", "destination"):
        floor_field = f"{prefix}_floor"
        access_field = f"{prefix}_access"
        floor = getattr(merged, floor_field)
        if floor == 1:
            setattr(merged, access_field, Access.NOT_APPLICABLE)
        elif floor and floor > 1 and getattr(merged, access_field) == Access.NOT_APPLICABLE:
            setattr(merged, access_field, None)
    validate_state(merged)
    return merged
