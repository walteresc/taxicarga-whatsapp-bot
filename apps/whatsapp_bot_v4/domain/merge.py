import logging
import unicodedata

from .state import Access, BotState
from .validators import DomainValidationError, validate_state, validate_value


logger = logging.getLogger(__name__)


def normalize_for_comparison(value) -> str:
    """Normalize string for comparison: lowercase, remove accents."""
    if not isinstance(value, str):
        return str(value)
    # Remove accents
    nfd = unicodedata.normalize('NFD', value)
    normalized = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    return normalized.lower().strip()


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

        # MERGE NO ATÓMICO: Comparar normalizado para detectar conflictos reales
        if current not in (None, [], ""):
            # Normalize both for comparison
            normalized_current = normalize_for_comparison(current)
            normalized_value = normalize_for_comparison(value)

            if normalized_current == normalized_value:
                # Same value (after normalization) → no-op, don't apply
                logger.debug(
                    "bot_v4_merge_noop field=%s current=%r value=%r "
                    "(same after normalization)",
                    field, current, value,
                )
                continue
            else:
                # Real conflict: log but DON'T fail, skip this field
                logger.warning(
                    "bot_v4_merge_conflict field=%s current=%r value=%r "
                    "skipping conflictive field, keeping current",
                    field, current, value,
                )
                continue  # Skip applying this conflictive value

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
