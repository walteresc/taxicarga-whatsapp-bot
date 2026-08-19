from dataclasses import asdict, dataclass, field
from enum import StrEnum


class Access(StrEnum):
    ELEVATOR = "ascensor"
    STAIRS = "escaleras"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class BotState:
    origin_district: str | None = None
    destination_district: str | None = None
    origin_floor: int | None = None
    destination_floor: int | None = None
    origin_access: Access | None = None
    destination_access: Access | None = None
    items: list[str] = field(default_factory=list)
    packing_modalidad: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def copy(self) -> "BotState":
        return BotState(**self.to_dict())

    @classmethod
    def from_dict(cls, payload: dict) -> "BotState":
        data = dict(payload or {})
        # Tolerate old data with request_boundary_at (moved to BotConversationState column)
        data.pop("request_boundary_at", None)
        for field_name in ("origin_access", "destination_access"):
            if data.get(field_name) is not None:
                data[field_name] = Access(data[field_name])
        data["items"] = list(data.get("items") or [])
        return cls(**data)
