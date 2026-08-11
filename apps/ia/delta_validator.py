from dataclasses import dataclass

from .delta_contract import ConversationDelta
from .delta_snapshot import CanonicalSnapshot


@dataclass(frozen=True)
class DeltaValidationResult:
    accepted: ConversationDelta
    rejected_fields: tuple[str, ...]
    rejection_reasons: tuple[str, ...]


def validate_delta(delta: ConversationDelta, snapshot: CanonicalSnapshot):
    valid_refs = set(snapshot.state["locations"])
    valid_refs.add("both")
    accepted_locations = []
    rejected = []
    reasons = []
    for index, location in enumerate(delta.changes.locations):
        ref = str(location.ref.value if hasattr(location.ref, "value") else location.ref)
        if ref not in valid_refs:
            rejected.append(f"changes.locations[{index}].ref")
            reasons.append("unknown_location_reference")
            continue
        if ref == "both" and len(valid_refs - {"both"}) < 2:
            rejected.append(f"changes.locations[{index}].ref")
            reasons.append("both_requires_two_locations")
            continue
        accepted_locations.append(location)
    accepted = delta.model_copy(deep=True)
    accepted.changes.locations = accepted_locations
    return DeltaValidationResult(
        accepted=accepted,
        rejected_fields=tuple(rejected),
        rejection_reasons=tuple(reasons),
    )


def snapshot_matches(lead, expected_version):
    from .delta_snapshot import build_canonical_snapshot

    return build_canonical_snapshot(lead).state_version == expected_version
