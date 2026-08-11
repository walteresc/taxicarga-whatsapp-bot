from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr


SCHEMA_VERSION = 1


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Intent(str, Enum):
    PROVIDE_INFORMATION = "provide_information"
    CORRECT_INFORMATION = "correct_information"
    ANSWER_QUESTION = "answer_question"
    ASK_QUESTION = "ask_question"
    OTHER = "other"


class LocationRef(str, Enum):
    ORIGIN = "origin"
    DESTINATION = "destination"
    BOTH = "both"


class LeadSet(StrictModel):
    service: Literal["mudanza", "oficina", "traslado pequeno", "carga"] | None = None
    load: StrictStr | None = Field(default=None, max_length=1000)
    staff_required: StrictBool | None = None
    packing: Literal[
        "sin embalaje",
        "embalaje basico",
        "embalaje de muebles y artefactos",
        "embalaje full",
    ] | None = None
    disassembly_required: StrictBool | None = None
    assembly_required: StrictBool | None = None


class LocationSet(StrictModel):
    district: StrictStr | None = Field(default=None, max_length=120)
    floor: StrictInt | None = Field(default=None, ge=1, le=100)
    elevator: StrictBool | None = None
    truck_access: StrictBool | None = None
    carry_distance_m: StrictInt | None = Field(default=None, ge=0, le=10000)
    access_observation: StrictStr | None = Field(default=None, max_length=500)


class LocationDelta(StrictModel):
    ref: StrictStr
    set: LocationSet


class Changes(StrictModel):
    lead: LeadSet = Field(default_factory=LeadSet)
    locations: list[LocationDelta] = Field(default_factory=list, max_length=20)


class Correction(StrictModel):
    target: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="explicit_customer_correction", max_length=160)


class Ambiguity(StrictModel):
    target: str = Field(min_length=1, max_length=120)
    alternatives: list[str] = Field(default_factory=list, max_length=10)


class ConversationDelta(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    intent: Intent
    changes: Changes = Field(default_factory=Changes)
    corrections: list[Correction] = Field(default_factory=list, max_length=20)
    ambiguities: list[Ambiguity] = Field(default_factory=list, max_length=20)


def conversation_delta_json_schema() -> dict[str, Any]:
    return ConversationDelta.model_json_schema()


def empty_delta() -> ConversationDelta:
    return ConversationDelta(intent=Intent.OTHER)
