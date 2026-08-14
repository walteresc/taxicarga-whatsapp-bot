from .state import Access, BotState


BASE_FIELDS = (
    "origin_district",
    "destination_district",
    "origin_floor",
    "destination_floor",
    "items",
)


def required_missing(state: BotState) -> list[str]:
    missing = [field for field in BASE_FIELDS if not getattr(state, field)]
    if state.origin_floor is not None and state.origin_floor > 1 and state.origin_access not in {Access.ELEVATOR, Access.STAIRS}:
        missing.append("origin_access")
    if state.destination_floor is not None and state.destination_floor > 1 and state.destination_access not in {Access.ELEVATOR, Access.STAIRS}:
        missing.append("destination_access")
    return missing


def ready_to_quote(state: BotState) -> bool:
    return not required_missing(state)
