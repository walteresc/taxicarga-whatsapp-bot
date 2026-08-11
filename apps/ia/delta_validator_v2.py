import re
import time
import unicodedata
from dataclasses import dataclass

from .delta_contract_v2 import AmbiguityV2, ConversationDeltaV2, EvidenceType, empty_delta_v2
from .delta_snapshot import CanonicalSnapshot


NO_EVIDENCE = "NO_EVIDENCE"
INFERRED_NOT_ALLOWED = "INFERRED_NOT_ALLOWED"
NO_OP = "NO_OP"
INVALID_REF = "INVALID_REF"
STALE_STATE = "STALE_STATE"
AMBIGUOUS_REF = "AMBIGUOUS_REF"
UNSUPPORTED_NORMALIZATION = "UNSUPPORTED_NORMALIZATION"


@dataclass(frozen=True)
class RejectedChange:
    path: str
    reason: str


@dataclass(frozen=True)
class DeltaValidationV2Result:
    proposed: ConversationDeltaV2
    accepted: ConversationDeltaV2
    rejected: tuple[RejectedChange, ...]
    latency_ms: float


def _norm(value):
    return " ".join(
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore").decode().lower().split()
    )


def _anchored(evidence, customer_message):
    return _norm(evidence) in _norm(customer_message)


def _snapshot_value(snapshot, path):
    value = snapshot.state
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _field_reason(proposal, customer_message, current_value, *, numeric=False):
    if proposal.evidence_type == EvidenceType.INFERRED:
        return INFERRED_NOT_ALLOWED
    if not _anchored(proposal.evidence, customer_message):
        return NO_EVIDENCE
    if numeric and not re.search(rf"(?<!\d){proposal.value}(?!\d)", proposal.evidence):
        return UNSUPPORTED_NORMALIZATION
    if proposal.value == current_value:
        return NO_OP
    return None


def _co_located(ref_evidence, value_evidence):
    ref_text = _norm(ref_evidence)
    value_text = _norm(value_evidence)
    return ref_text in value_text or value_text in ref_text


def validate_delta_v2(
    delta, snapshot: CanonicalSnapshot, *, customer_message,
    last_bot_question="", expected_state_version=None,
):
    started = time.perf_counter()
    accepted = empty_delta_v2().model_copy(update={"intent": delta.intent})
    accepted.ambiguities = [
        item for item in delta.ambiguities if _anchored(item.evidence, customer_message)
    ]
    rejected = []
    if expected_state_version and snapshot.state_version != expected_state_version:
        return DeltaValidationV2Result(delta, accepted, (RejectedChange("*", STALE_STATE),),
                                       (time.perf_counter() - started) * 1000)

    correction_targets = {
        item.target for item in delta.corrections
        if item.evidence_type != EvidenceType.INFERRED and _anchored(item.evidence, customer_message)
    }
    for field, proposal in delta.changes.lead:
        if proposal is None:
            continue
        path_map = {
            "service": "service", "load": "load", "staff_required": "staff.required",
            "packing": "additional_services.packing",
            "disassembly_required": "additional_services.disassembly_required",
            "assembly_required": "additional_services.assembly_required",
        }
        path = path_map[field]
        reason = _field_reason(proposal, customer_message, _snapshot_value(snapshot, path))
        if reason == NO_OP and path in correction_targets:
            reason = None
        if reason:
            rejected.append(RejectedChange(path, reason))
        else:
            setattr(accepted.changes.lead, field, proposal)

    valid_refs = set(snapshot.state.get("locations", {}))
    candidates = []
    for index, location in enumerate(delta.changes.locations):
        ref = location.ref
        if ref not in valid_refs | {"both"}:
            rejected.append(RejectedChange(f"changes.locations[{index}].ref", INVALID_REF))
            continue
        if ref == "both" and not last_bot_question and not all(
            _norm(location.ref_evidence).find(_norm(snapshot.state["locations"][endpoint].get("district"))) >= 0
            for endpoint in ("origin", "destination")
            if endpoint in snapshot.state["locations"]
        ):
            rejected.append(RejectedChange(f"changes.locations[{index}].ref", AMBIGUOUS_REF))
            for field, proposal in location.set:
                if field == "access_observation" and proposal is not None:
                    accepted.ambiguities.append(AmbiguityV2(
                        field=field, value=str(proposal.value),
                        possible_refs=sorted(valid_refs), evidence=proposal.evidence,
                    ))
            continue
        if not _anchored(location.ref_evidence, customer_message):
            rejected.append(RejectedChange(f"changes.locations[{index}].ref", NO_EVIDENCE))
            continue
        if location.ref_evidence_type == EvidenceType.INFERRED:
            rejected.append(RejectedChange(f"changes.locations[{index}].ref", INFERRED_NOT_ALLOWED))
            continue
        refs = ["origin", "destination"] if ref == "both" else [ref]
        for field, proposal in location.set:
            if proposal is None:
                continue
            candidates.append((index, location, refs, field, proposal))

    accepted_locations = {}
    for index, location, refs, field, proposal in candidates:
        if not _co_located(location.ref_evidence, proposal.evidence):
            rejected.append(RejectedChange(f"changes.locations[{index}].set.{field}", AMBIGUOUS_REF))
            if field == "access_observation" and not any(
                item.field == field and item.evidence == proposal.evidence
                for item in accepted.ambiguities
            ):
                accepted.ambiguities.append(AmbiguityV2(
                    field=field,
                    value=str(proposal.value),
                    possible_refs=sorted(valid_refs),
                    evidence=proposal.evidence,
                ))
            continue
        for ref in refs:
            path = f"locations.{ref}.{field}"
            reason = _field_reason(
                proposal, customer_message, _snapshot_value(snapshot, path),
                numeric=field == "carry_distance_m",
            )
            if reason == NO_OP and path in correction_targets:
                reason = None
            if reason:
                rejected.append(RejectedChange(path, reason))
                continue
            target = accepted_locations.get((location.ref, location.ref_evidence, location.ref_evidence_type))
            if target is None:
                target = location.model_copy(deep=True)
                target.set = type(location.set)()
                accepted_locations[(location.ref, location.ref_evidence, location.ref_evidence_type)] = target
            setattr(target.set, field, proposal)
    accepted.changes.locations = list(accepted_locations.values())
    accepted.corrections = [
        item for item in delta.corrections
        if item.target in correction_targets
    ]
    return DeltaValidationV2Result(
        delta, accepted, tuple(rejected), (time.perf_counter() - started) * 1000
    )
