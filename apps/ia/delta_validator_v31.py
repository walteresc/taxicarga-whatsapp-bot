import re
import unicodedata
from dataclasses import dataclass

from .conversation_policy import QuestionTarget
from .delta_contract_v31 import (
    Ambiguity31, ContextDependency, Correction31, EvidenceType, RefSource, ValueOrigin,
    empty_delta_v31,
)
from .delta_validator_v2 import RejectedChange


INFERRED_NOT_ALLOWED = "INFERRED_NOT_ALLOWED"
CONTEXT_TARGET_MISMATCH = "CONTEXT_TARGET_MISMATCH"
NO_EVIDENCE = "NO_EVIDENCE"
AMBIGUOUS_REF = "AMBIGUOUS_REF"
INVALID_REF = "INVALID_REF"
DERIVED_VALUE_FORBIDDEN = "DERIVED_VALUE_FORBIDDEN"
UNSUPPORTED_MEASUREMENT = "UNSUPPORTED_MEASUREMENT"
UNSUPPORTED_BOOLEAN_EVIDENCE = "UNSUPPORTED_BOOLEAN_EVIDENCE"
UNSUPPORTED_SERVICE_EVIDENCE = "UNSUPPORTED_SERVICE_EVIDENCE"
AMBIGUOUS_BOOLEAN_EVIDENCE = "AMBIGUOUS_BOOLEAN_EVIDENCE"
NO_OP = "NO_OP"
STALE_STATE = "STALE_STATE"
EVIDENCE_CLAIM_COLLISION = "EVIDENCE_CLAIM_COLLISION"
UNVERIFIED_EXPLICIT_REF = "UNVERIFIED_EXPLICIT_REF"

_SPANISH_NUMBERS = {
    "cero":0,"primer":1,"primero":1,"primera":1,"uno":1,"un":1,
    "segundo":2,"segunda":2,"dos":2,"tercer":3,"tercero":3,"tercera":3,"tres":3,
    "cuarto":4,"cuarta":4,"cuatro":4,"quinto":5,"quinta":5,"cinco":5,
    "sexto":6,"sexta":6,"seis":6,"septimo":7,"septima":7,"siete":7,
    "octavo":8,"octava":8,"ocho":8,"noveno":9,"novena":9,"nueve":9,
    "decimo":10,"decima":10,"diez":10,
    "once":11,"doce":12,"trece":13,"catorce":14,"quince":15,
    "dieciseis":16,"diecisiete":17,"dieciocho":18,"diecinueve":19,"veinte":20,
    "baja":0,
}


@dataclass(frozen=True)
class DeltaValidationV31Result:
    proposed: object
    accepted: object
    rejected: tuple[RejectedChange, ...]


def _anchored(evidence, message):
    return bool(evidence) and evidence in message


def _normalized_number_is_anchored(value, evidence):
    normalized = unicodedata.normalize("NFKD", evidence.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    words = re.findall(r"[^\W\d_]+", normalized, flags=re.UNICODE)
    return any(_SPANISH_NUMBERS.get(word) == value for word in words)


def _target_matches(targets, field, ref=None):
    compatible = {field}
    if field == "access_observation":
        compatible.add("truck_access")
    if field == "packing_required":
        compatible.add("packing_mode")
    return any(target.field in compatible and
               (target.ref in (None, "both") or ref in (None, target.ref))
               for target in targets)


def _explicit_ref_marker_is_anchored(ref, evidence):
    normalized = unicodedata.normalize("NFKD", evidence.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    words = set(re.findall(r"[^\W\d_]+", normalized, flags=re.UNICODE))
    markers = {
        "origin":{"origen","salida","sale","recojo","recoger","carga","desde",
                  "primer","primero","primera","aca","aqui","salimos","partimos",
                  "partir"},
        "destination":{"destino","llegada","llega","entrega","descarga","hasta",
                       "segundo","segunda","alla","aya","llegamos","llegar"},
        "both":{"ambos","ambas"},
    }
    return bool(words & markers.get(ref,set()))


def _ref_both_conflicts_with_specific_marker(evidence):
    return (_explicit_ref_marker_is_anchored("origin",evidence)
            or _explicit_ref_marker_is_anchored("destination",evidence)) and not (
                _explicit_ref_marker_is_anchored("both",evidence))


def _truck_access_evidence_valid(proposal):
    normalized=unicodedata.normalize("NFKD",proposal.evidence_quote.casefold())
    normalized="".join(char for char in normalized if not unicodedata.combining(char))
    words=set(re.findall(r"[^\W\d_]+",normalized,flags=re.UNICODE))
    negative=bool(words & {"no","nunca","tampoco","imposible","ninguno","ninguna"})
    access=bool(words & {"entra","entrar","ingresa","ingresar","accede","acceso"})
    contextual=proposal.context_dependency == ContextDependency.QUESTION_TARGET
    polarity=(proposal.value is False and negative) or (proposal.value is True and not negative)
    return polarity and (access or contextual)


def _service_evidence_valid(proposal):
    normalized=unicodedata.normalize("NFKD",proposal.evidence_quote.casefold())
    normalized="".join(char for char in normalized if not unicodedata.combining(char))
    words=set(re.findall(r"[^\W\d_]+",normalized,flags=re.UNICODE))
    markers={
        "mudanza":{"mudanza","mudar","mudo","mudamos"},
        "oficina":{"oficina","empresa","empresarial"},
        "traslado pequeno":{"traslado","trasladar","transportar","mover","muevo","movere"},
        "carga":{"carga","mercaderia","pallet","pallets"},
    }
    if proposal.value == "traslado pequeno" and "solo" in words and words & {"llevar","llevo"}:
        return True
    return bool(words & markers.get(proposal.value,set()))


def _boolean_evidence_is_uncertain(proposal):
    value=getattr(proposal,"value",getattr(proposal,"new",None))
    if not isinstance(value,bool):
        return False
    normalized=unicodedata.normalize("NFKD",proposal.evidence_quote.casefold())
    normalized="".join(char for char in normalized if not unicodedata.combining(char))
    words=set(re.findall(r"[^\W\d_]+",normalized,flags=re.UNICODE))
    return bool(words & {"quizas","quiza","talvez","duda","dudando"}) or (
        "tal" in words and "vez" in words) or ("no" in words and "se" in words) or (
        "no" in words and "decido" in words)


def _normalized_service_date(value,evidence):
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):
        return value
    normalized=unicodedata.normalize("NFKD",evidence.casefold())
    normalized="".join(char for char in normalized if not unicodedata.combining(char))
    words=set(re.findall(r"[^\W\d_]+",normalized,flags=re.UNICODE))
    weekdays={"lunes":"monday","martes":"tuesday","miercoles":"wednesday",
              "jueves":"thursday","viernes":"friday","sabado":"saturday",
              "domingo":"sunday"}
    for spanish,english in weekdays.items():
        if spanish in words:return f"relative:{english}"
    if "manana" in words:return "relative:tomorrow"
    return value


def _state_value(snapshot, path):
    value = snapshot.state
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _proposal_reason(proposal, message, targets, field, ref=None, *, check_context=True):
    if proposal.evidence_type == EvidenceType.INFERRED:
        return INFERRED_NOT_ALLOWED
    if not _anchored(proposal.evidence_quote, message):
        return NO_EVIDENCE
    if _boolean_evidence_is_uncertain(proposal):
        return AMBIGUOUS_BOOLEAN_EVIDENCE
    if (check_context and proposal.context_dependency == ContextDependency.QUESTION_TARGET
            and not _target_matches(targets, field, ref)):
        return CONTEXT_TARGET_MISMATCH
    if hasattr(proposal, "value_origin"):
        if proposal.value_origin == ValueOrigin.DERIVED:
            return DERIVED_VALUE_FORBIDDEN
        directly_anchored = re.search(
            rf"(?<!\d){proposal.value}(?!\d)", proposal.evidence_quote)
        normalized_anchored = _normalized_number_is_anchored(
            proposal.value, proposal.evidence_quote)
        if not directly_anchored and not normalized_anchored:
            return UNSUPPORTED_MEASUREMENT
    return None


def validate_delta_v31(delta, snapshot, *, customer_message, question_targets=(),
                       expected_state_version=None):
    targets = tuple(target if isinstance(target, QuestionTarget) else QuestionTarget(**target)
                    for target in question_targets)
    accepted = empty_delta_v31().model_copy(update={"intent": delta.intent})
    rejected = []
    if expected_state_version and expected_state_version != snapshot.state_version:
        return DeltaValidationV31Result(delta, accepted,
                                        (RejectedChange("*", STALE_STATE),))

    lead_paths = {
        "service":"service", "service_date":"service_date", "load":"load",
        "staff_required":"staff.required",
        "packing_required":"additional_services.packing_required",
        "packing_mode":"additional_services.packing",
        "disassembly_required":"additional_services.disassembly_required",
        "assembly_required":"additional_services.assembly_required",
    }
    correction_targets = set()
    for correction in delta.corrections:
        reason = _proposal_reason(correction, customer_message, targets,
                                  correction.target.split(".")[-1],
                                  check_context=False)
        if reason:
            rejected.append(RejectedChange(f"corrections.{correction.target}", reason))
        else:
            accepted.corrections.append(correction)
            correction_targets.add(correction.target)

    targeted_claim_quotes = {
        proposal.evidence_quote
        for field, proposal in delta.changes.lead
        if proposal is not None and _target_matches(targets, field)
    }

    for field, proposal in delta.changes.lead:
        if proposal is None:
            continue
        reason = _proposal_reason(proposal, customer_message, targets, field)
        if not reason and field == "service" and not _service_evidence_valid(proposal):
            reason = UNSUPPORTED_SERVICE_EVIDENCE
        collision_prone_neighbor = (
            field == "load" and any(target.field in {"packing_required","packing_mode"}
                                    for target in targets)
            or field == "service" and any(target.field == "staff_required"
                                           for target in targets))
        if (not reason and collision_prone_neighbor and not _target_matches(targets, field)
                and proposal.evidence_quote in targeted_claim_quotes):
            reason = EVIDENCE_CLAIM_COLLISION
        path = lead_paths[field]
        if not reason and proposal.value == _state_value(snapshot, path) and path not in correction_targets:
            reason = NO_OP
        if reason:
            rejected.append(RejectedChange(path, reason))
        else:
            kept=proposal.model_copy(deep=True)
            if field == "service_date":
                kept.value=_normalized_service_date(kept.value,kept.evidence_quote)
            setattr(accepted.changes.lead, field, kept)
            if delta.intent.value == "correct_information" and path not in correction_targets:
                accepted.corrections.append(Correction31(
                    target=path,old=_state_value(snapshot,path),new=kept.value,
                    evidence_quote=kept.evidence_quote,evidence_type=kept.evidence_type,
                    context_dependency=ContextDependency.NONE))
                correction_targets.add(path)

    valid_refs = set(snapshot.state.get("locations", {}))
    ambiguous_fields = {item.field for item in delta.ambiguities}
    for index, location in enumerate(delta.changes.locations):
        ref = location.ref
        if ref not in valid_refs | {"both"}:
            rejected.append(RejectedChange(f"changes.locations[{index}].ref", INVALID_REF)); continue
        refs = ("origin", "destination") if ref == "both" else (ref,)
        fields = [field for field, proposal in location.set if proposal is not None]
        explicit_ref_marker = _explicit_ref_marker_is_anchored(
            ref,location.ref_evidence_quote)
        if location.ref_source == RefSource.AMBIGUOUS and not explicit_ref_marker:
            for field in fields or ["location"]:
                accepted.ambiguities.append(Ambiguity31(
                    field=field, value=location.ref_evidence_quote,
                    possible_refs=sorted(valid_refs),
                    evidence_quote=location.ref_evidence_quote))
            rejected.append(RejectedChange(f"changes.locations[{index}].ref", AMBIGUOUS_REF)); continue
        if not _anchored(location.ref_evidence_quote, customer_message):
            rejected.append(RejectedChange(f"changes.locations[{index}].ref", NO_EVIDENCE)); continue
        target_resolves_ref = any(
            _target_matches(targets, field, endpoint)
            for field in fields for endpoint in refs)
        if (location.ref_source == RefSource.EXPLICIT_MESSAGE
                and any(field != "district" for field in fields)
                and not target_resolves_ref
                and not explicit_ref_marker):
            for field in fields:
                accepted.ambiguities.append(Ambiguity31(
                    field=field,value=location.ref_evidence_quote,
                    possible_refs=sorted(valid_refs),
                    evidence_quote=location.ref_evidence_quote))
            rejected.append(RejectedChange(
                f"changes.locations[{index}].ref",UNVERIFIED_EXPLICIT_REF)); continue
        if (location.ref_source == RefSource.QUESTION_TARGET
                and not explicit_ref_marker and not any(
                _target_matches(targets, field, endpoint)
                for field in fields for endpoint in refs)):
            rejected.append(RejectedChange(f"changes.locations[{index}].ref",
                                           CONTEXT_TARGET_MISMATCH)); continue
        kept = location.model_copy(deep=True); kept.set = type(location.set)()
        for field, proposal in location.set:
            if proposal is None:
                continue
            reason = None
            ref_is_resolved = (explicit_ref_marker
                or (location.ref_source == RefSource.QUESTION_TARGET
                    and ref != "both" and _target_matches(targets,field,ref)))
            if field in ambiguous_fields and not ref_is_resolved:
                reason = AMBIGUOUS_REF
            if (not reason and ref == "both"
                    and _ref_both_conflicts_with_specific_marker(
                        location.ref_evidence_quote)):
                reason = AMBIGUOUS_REF
            if (not reason and field == "truck_access"
                    and not _truck_access_evidence_valid(proposal)):
                reason = UNSUPPORTED_BOOLEAN_EVIDENCE
            for endpoint in refs:
                if not reason:
                    reason = _proposal_reason(
                        proposal, customer_message, targets, field, endpoint)
                if (reason == CONTEXT_TARGET_MISMATCH
                        and proposal.evidence_type == EvidenceType.EXPLICIT
                        and _explicit_ref_marker_is_anchored(
                            endpoint,location.ref_evidence_quote)):
                    reason = _proposal_reason(
                        proposal,customer_message,targets,field,endpoint,
                        check_context=False)
                if reason:
                    break
                path = f"locations.{endpoint}.{field}"
                if proposal.value == _state_value(snapshot, path) and path not in correction_targets:
                    reason = NO_OP
                    break
            if reason:
                rejected.append(RejectedChange(f"locations.{ref}.{field}", reason))
            else:
                setattr(kept.set, field, proposal)
        if any(value is not None for _, value in kept.set):
            accepted.changes.locations.append(kept)
            if delta.intent.value == "correct_information":
                for field,proposal in kept.set:
                    if proposal is None:continue
                    for endpoint in refs:
                        path=f"locations.{endpoint}.{field}"
                        if path in correction_targets:continue
                        accepted.corrections.append(Correction31(
                            target=path,old=_state_value(snapshot,path),new=proposal.value,
                            evidence_quote=proposal.evidence_quote,
                            evidence_type=proposal.evidence_type,
                            context_dependency=ContextDependency.NONE))
                        correction_targets.add(path)
    accepted.ambiguities.extend(delta.ambiguities)
    return DeltaValidationV31Result(delta, accepted, tuple(rejected))
