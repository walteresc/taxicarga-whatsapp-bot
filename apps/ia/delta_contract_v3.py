from typing import Literal

from pydantic import Field

from .delta_contract import Intent
from .delta_contract_v2 import (
    AmbiguityV2, CorrectionV2, EvidenceBool, EvidencePacking, EvidenceService,
    EvidenceStr, LocationDeltaV2, StrictModel,
)


SCHEMA_VERSION = 3


class LeadEvidenceSetV3(StrictModel):
    service: EvidenceService | None = None
    load: EvidenceStr | None = None
    staff_required: EvidenceBool | None = None
    packing_required: EvidenceBool | None = None
    packing_mode: EvidencePacking | None = None
    disassembly_required: EvidenceBool | None = None
    assembly_required: EvidenceBool | None = None


class ChangesV3(StrictModel):
    lead: LeadEvidenceSetV3 = Field(default_factory=LeadEvidenceSetV3)
    locations: list[LocationDeltaV2] = Field(default_factory=list, max_length=20)


class ConversationDeltaV3(StrictModel):
    schema_version: Literal[3] = SCHEMA_VERSION
    intent: Intent
    changes: ChangesV3 = Field(default_factory=ChangesV3)
    corrections: list[CorrectionV2] = Field(default_factory=list, max_length=20)
    ambiguities: list[AmbiguityV2] = Field(default_factory=list, max_length=20)


def empty_delta_v3():
    return ConversationDeltaV3(intent=Intent.OTHER)
