from dataclasses import dataclass

from .conversation_policy import QuestionTarget
from .delta_contract_v2 import AmbiguityV2, EvidenceType, empty_delta_v2
from .delta_validator_v2 import RejectedChange, validate_delta_v2


CONTEXT_TARGET_MISMATCH = "CONTEXT_TARGET_MISMATCH"
ATTRIBUTE_CLOSURE = "ATTRIBUTE_CLOSURE"
UNSUPPORTED_SPECIFICITY = "UNSUPPORTED_SPECIFICITY"
AMBIGUOUS_REF = "AMBIGUOUS_REF"
DERIVED_FIELD_FORBIDDEN = "DERIVED_FIELD_FORBIDDEN"
NO_OP = "NO_OP"
FORBIDDEN_FIELD = "FORBIDDEN_FIELD"
STALE_STATE = "STALE_STATE"
INVALID_REF = "INVALID_REF"
INVALID_TYPE = "INVALID_TYPE"
TARGET_METADATA_UNAVAILABLE = "TARGET_METADATA_UNAVAILABLE"


FIELD_CLASSES = {
    "service": "identity", "district": "route", "floor": "direct_physical",
    "elevator": "direct_physical", "staff_required": "service_option",
    "packing": "service_option", "disassembly_required": "service_option",
    "assembly_required": "service_option", "load": "observational",
    "access_observation": "observational", "truck_access": "derived",
    "carry_distance_m": "derived",
}


@dataclass(frozen=True)
class DeltaValidationV3Result:
    proposed: object
    accepted: object
    rejected: tuple[RejectedChange, ...]
    target_metadata_available: bool


def _matches_target(targets, field, ref=None):
    aliases = {"packing": {"packing", "packing_mode"},
               "staff_required": {"staff_required", "staff_quantity"}}
    names = aliases.get(field, {field})
    return any(target.field in names and (
        target.ref in (None, "both") or ref in (None, target.ref)
    ) for target in targets)


def _normalize_contextual(delta, targets):
    normalized = delta.model_copy(deep=True)
    for field, proposal in normalized.changes.lead:
        if proposal and proposal.evidence_type == EvidenceType.INFERRED and _matches_target(targets, field):
            proposal.evidence_type = EvidenceType.EXPLICIT_CONTEXTUAL
    for location in normalized.changes.locations:
        matching = False
        for field, proposal in location.set:
            if proposal and _matches_target(targets, field, location.ref):
                matching = True
                if proposal.evidence_type == EvidenceType.INFERRED:
                    proposal.evidence_type = EvidenceType.EXPLICIT_CONTEXTUAL
        if matching and location.ref_evidence_type == EvidenceType.INFERRED:
            location.ref_evidence_type = EvidenceType.EXPLICIT_CONTEXTUAL
    return normalized


def validate_delta_v3(delta, snapshot, *, customer_message, question_targets=(),
                      expected_state_version=None):
    targets = tuple(
        target if isinstance(target, QuestionTarget) else QuestionTarget(**target)
        for target in question_targets
    )
    normalized = _normalize_contextual(delta, targets)
    v2 = validate_delta_v2(
        normalized, snapshot, customer_message=customer_message,
        last_bot_question="structured-target" if targets else "",
        expected_state_version=expected_state_version,
    )
    accepted = empty_delta_v2().model_copy(update={"intent": v2.accepted.intent})
    accepted.ambiguities = list(v2.accepted.ambiguities)
    rejected = list(v2.rejected)
    for field, proposal in v2.accepted.changes.lead:
        if proposal is None:
            continue
        if field == "service" and proposal.evidence_type != EvidenceType.EXPLICIT and not _matches_target(targets, field):
            rejected.append(RejectedChange(field, ATTRIBUTE_CLOSURE)); continue
        if field == "packing" and any(target.field == "packing_required" for target in targets):
            rejected.append(RejectedChange(field, UNSUPPORTED_SPECIFICITY)); continue
        if proposal.evidence_type == EvidenceType.EXPLICIT_CONTEXTUAL and not _matches_target(targets, field):
            rejected.append(RejectedChange(field, CONTEXT_TARGET_MISMATCH)); continue
        setattr(accepted.changes.lead, field, proposal)
    kept_locations = []
    for location in v2.accepted.changes.locations:
        kept = location.model_copy(deep=True); kept.set = type(location.set)()
        for field, proposal in location.set:
            if proposal is None:
                continue
            if FIELD_CLASSES.get(field) == "derived":
                rejected.append(RejectedChange(f"locations.{location.ref}.{field}", DERIVED_FIELD_FORBIDDEN)); continue
            if (field == "access_observation" and not _matches_target(targets, field, location.ref)
                    and location.ref_evidence.strip() == proposal.evidence.strip()):
                rejected.append(RejectedChange(f"locations.{location.ref}.{field}", AMBIGUOUS_REF))
                accepted.ambiguities.append(AmbiguityV2(
                    field=field, value=str(proposal.value),
                    possible_refs=["origin", "destination"], evidence=proposal.evidence,
                ))
                continue
            if proposal.evidence_type == EvidenceType.EXPLICIT_CONTEXTUAL and not _matches_target(targets, field, location.ref):
                rejected.append(RejectedChange(f"locations.{location.ref}.{field}", CONTEXT_TARGET_MISMATCH)); continue
            setattr(kept.set, field, proposal)
        if any(value is not None for _, value in kept.set):
            kept_locations.append(kept)
    accepted.changes.locations = kept_locations
    accepted.corrections = list(v2.accepted.corrections)
    return DeltaValidationV3Result(delta, accepted, tuple(rejected), bool(targets))
