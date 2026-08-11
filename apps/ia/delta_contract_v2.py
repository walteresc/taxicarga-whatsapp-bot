from enum import Enum
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr

from .delta_contract import Intent, StrictModel


SCHEMA_VERSION = 2


class EvidenceType(str, Enum):
    EXPLICIT = "explicit"
    EXPLICIT_CONTEXTUAL = "explicit_contextual"
    INFERRED = "inferred"


class EvidenceMeta(StrictModel):
    evidence: StrictStr = Field(min_length=1, max_length=500)
    evidence_type: EvidenceType


class EvidenceBool(EvidenceMeta):
    value: StrictBool


class EvidenceInt(EvidenceMeta):
    value: StrictInt


class EvidenceStr(EvidenceMeta):
    value: StrictStr = Field(min_length=1, max_length=1000)


class EvidenceService(EvidenceMeta):
    value: Literal["mudanza", "oficina", "traslado pequeno", "carga"]


class EvidencePacking(EvidenceMeta):
    value: Literal[
        "sin embalaje",
        "embalaje basico",
        "embalaje de muebles y artefactos",
        "embalaje full",
    ]


class LeadEvidenceSet(StrictModel):
    service: EvidenceService | None = None
    load: EvidenceStr | None = None
    staff_required: EvidenceBool | None = None
    packing: EvidencePacking | None = None
    disassembly_required: EvidenceBool | None = None
    assembly_required: EvidenceBool | None = None


class LocationEvidenceSet(StrictModel):
    district: EvidenceStr | None = None
    floor: EvidenceInt | None = None
    elevator: EvidenceBool | None = None
    truck_access: EvidenceBool | None = None
    carry_distance_m: EvidenceInt | None = None
    access_observation: EvidenceStr | None = None


class LocationDeltaV2(StrictModel):
    ref: StrictStr
    ref_evidence: StrictStr = Field(min_length=1, max_length=300)
    ref_evidence_type: EvidenceType
    set: LocationEvidenceSet


class ChangesV2(StrictModel):
    lead: LeadEvidenceSet = Field(default_factory=LeadEvidenceSet)
    locations: list[LocationDeltaV2] = Field(default_factory=list, max_length=20)


class CorrectionV2(StrictModel):
    target: StrictStr = Field(min_length=1, max_length=120)
    old: StrictStr | StrictInt | StrictBool | None = None
    new: StrictStr | StrictInt | StrictBool
    evidence: StrictStr = Field(min_length=1, max_length=500)
    evidence_type: EvidenceType


class AmbiguityV2(StrictModel):
    field: StrictStr = Field(min_length=1, max_length=120)
    value: StrictStr = Field(min_length=1, max_length=500)
    possible_refs: list[StrictStr] = Field(default_factory=list, min_length=2, max_length=10)
    evidence: StrictStr = Field(min_length=1, max_length=500)


class ConversationDeltaV2(StrictModel):
    schema_version: Literal[2] = SCHEMA_VERSION
    intent: Intent
    changes: ChangesV2 = Field(default_factory=ChangesV2)
    corrections: list[CorrectionV2] = Field(default_factory=list, max_length=20)
    ambiguities: list[AmbiguityV2] = Field(default_factory=list, max_length=20)


def empty_delta_v2():
    return ConversationDeltaV2(intent=Intent.OTHER)
