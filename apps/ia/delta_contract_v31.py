from enum import Enum
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr

from .delta_contract import Intent, StrictModel


class EvidenceType(str, Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class ContextDependency(str, Enum):
    NONE = "none"
    QUESTION_TARGET = "question_target"


class RefSource(str, Enum):
    EXPLICIT_MESSAGE = "explicit_message"
    QUESTION_TARGET = "question_target"
    AMBIGUOUS = "ambiguous"


class ValueOrigin(str, Enum):
    DIRECT = "direct"
    NORMALIZED_UNIT = "normalized_unit"
    DERIVED = "derived"


class EvidenceMeta31(StrictModel):
    evidence_quote: StrictStr = Field(min_length=1, max_length=500)
    evidence_type: EvidenceType
    context_dependency: ContextDependency = ContextDependency.NONE


class EvidenceBool31(EvidenceMeta31):
    value: StrictBool


class EvidenceInt31(EvidenceMeta31):
    value: StrictInt
    value_origin: ValueOrigin = ValueOrigin.DIRECT


class EvidenceStr31(EvidenceMeta31):
    value: StrictStr = Field(min_length=1, max_length=1000)


class EvidenceService31(EvidenceMeta31):
    value: Literal["mudanza", "oficina", "traslado pequeno", "carga"]


class EvidencePacking31(EvidenceMeta31):
    value: Literal["sin embalaje", "embalaje basico",
                   "embalaje de muebles y artefactos", "embalaje full"]


class LeadEvidenceSet31(StrictModel):
    service: EvidenceService31 | None = None
    service_date: EvidenceStr31 | None = None
    load: EvidenceStr31 | None = None
    staff_required: EvidenceBool31 | None = None
    packing_required: EvidenceBool31 | None = None
    packing_mode: EvidencePacking31 | None = None
    disassembly_required: EvidenceBool31 | None = None
    assembly_required: EvidenceBool31 | None = None


class LocationEvidenceSet31(StrictModel):
    district: EvidenceStr31 | None = None
    floor: EvidenceInt31 | None = None
    elevator: EvidenceBool31 | None = None
    truck_access: EvidenceBool31 | None = None
    carry_distance_m: EvidenceInt31 | None = None
    access_observation: EvidenceStr31 | None = None


class LocationDelta31(StrictModel):
    ref: StrictStr
    ref_evidence_quote: StrictStr = Field(min_length=1, max_length=300)
    ref_source: RefSource
    set: LocationEvidenceSet31


class Changes31(StrictModel):
    lead: LeadEvidenceSet31 = Field(default_factory=LeadEvidenceSet31)
    locations: list[LocationDelta31] = Field(default_factory=list, max_length=20)


class Correction31(EvidenceMeta31):
    target: StrictStr = Field(min_length=1, max_length=120)
    old: StrictStr | StrictInt | StrictBool | None = None
    new: StrictStr | StrictInt | StrictBool


class Ambiguity31(StrictModel):
    field: StrictStr
    value: StrictStr
    possible_refs: list[StrictStr] = Field(min_length=2, max_length=10)
    evidence_quote: StrictStr


class ConversationDeltaV31(StrictModel):
    schema_version: Literal["3.1"] = "3.1"
    intent: Intent
    changes: Changes31 = Field(default_factory=Changes31)
    corrections: list[Correction31] = Field(default_factory=list, max_length=20)
    ambiguities: list[Ambiguity31] = Field(default_factory=list, max_length=20)


def empty_delta_v31():
    return ConversationDeltaV31(intent=Intent.OTHER)
