import logging
from datetime import date

from django.db import transaction

from apps.integrations.models import ChannelIntegrationPolicy

from .delta_context import build_delta_context
from .delta_extractor_v31 import extract_conversation_delta_v31
from .delta_snapshot import build_canonical_snapshot
from .delta_validator_v31 import validate_delta_v31
from .models import AIDeltaAudit


logger=logging.getLogger(__name__)


def _safe(value):
    import re
    if isinstance(value,dict):return {key:_safe(item) for key,item in value.items()}
    if isinstance(value,list):return [_safe(item) for item in value]
    if isinstance(value,str):
        value=re.sub(r"[\w.+-]+@[\w.-]+","[redacted-email]",value)
        value=re.sub(r"\b(?:\+?51)?9\d{8}\b","[redacted-phone]",value)
        value=re.sub(r"\b\d{8}\b","[redacted-document]",value)
    return value


def _audit_state(snapshot):
    state=snapshot.state
    return _safe({"schema_version":state.get("schema_version"),
        "service":state.get("service"),"locations":state.get("locations",{}),
        "staff":state.get("staff",{}),
        "additional_services":state.get("additional_services",{})})


def record_runtime_state_after(audit,lead):
    audit.canonical_state_after=_audit_state(build_canonical_snapshot(lead))
    audit.save(update_fields=["canonical_state_after"])


def _legacy_fields(delta):
    result={}
    lead_map={"service":"tipo_servicio","service_date":"fecha_servicio",
              "load":"lista_objetos","staff_required":"incluye_personal_carga",
              "packing_mode":"modalidad_servicio",
              "disassembly_required":"requiere_desarmado",
              "assembly_required":"requiere_armado"}
    for field,proposal in delta.changes.lead:
        if proposal is None:continue
        target=lead_map.get(field)
        if target == "fecha_servicio":
            try:result[target]=date.fromisoformat(proposal.value)
            except (TypeError,ValueError):pass
        elif target:result[target]=proposal.value
        elif field == "packing_required" and proposal.value is False:
            result["modalidad_servicio"]="sin embalaje"
    location_map={"district":"distrito","floor":"piso","elevator":"ascensor",
                  "truck_access":"camion_llega","carry_distance_m":"distancia_carga",
                  "access_observation":"acceso"}
    for location in delta.changes.locations:
        refs=("origin","destination") if location.ref == "both" else (location.ref,)
        for ref in refs:
            suffix={"origin":"origen","destination":"destino"}.get(ref)
            if not suffix:continue
            for field,proposal in location.set:
                if proposal is None:continue
                base=location_map[field]
                key=(f"{base}_{suffix}_m" if field == "carry_distance_m"
                     else f"{base}_{suffix}")
                result[key]=proposal.value
    return result


def extract_runtime_v31(*,lead,conversation_id,message_id,customer_message,mode):
    """Extract validated V3.1 fields. It never mutates commercial state."""
    existing=AIDeltaAudit.objects.filter(message_id=message_id).first()
    if existing:
        return _audit_fields(existing),existing
    snapshot=build_canonical_snapshot(lead)
    context=build_delta_context(conversation_id,trigger_message_id=message_id,
                                customer_message=customer_message,snapshot=snapshot)
    try:
        delta,metrics=extract_conversation_delta_v31(context)
        validation=validate_delta_v31(delta,snapshot,customer_message=customer_message,
            question_targets=context.question_targets,expected_state_version=snapshot.state_version)
        accepted=validation.accepted.model_dump(mode="json",exclude_none=True)
        fields=_legacy_fields(validation.accepted)
        with transaction.atomic():
            audit=AIDeltaAudit.objects.create(
                conversation_id=conversation_id,message_id=message_id,lead=lead,
                provider=metrics.provider,model=metrics.model,schema_version=31,
                state_version=snapshot.state_version,mode=mode,
                status=(AIDeltaAudit.STATUS_REJECTED if validation.rejected
                        else AIDeltaAudit.STATUS_ACCEPTED),accepted_delta=accepted,
                raw_delta=_safe(delta.model_dump(mode="json",exclude_none=True)),
                rejected_delta=[{"path":item.path,"reason":item.reason}
                                for item in validation.rejected],
                question_targets=_safe(list(context.question_targets)),
                canonical_state_before=_audit_state(snapshot),
                rejected_fields=[item.path for item in validation.rejected],
                rejection_reasons=[item.reason for item in validation.rejected],
                latency_ms=metrics.latency_ms,input_tokens=metrics.input_tokens,
                output_tokens=metrics.output_tokens)
        return fields,audit
    except Exception as exc:
        logger.warning("V3.1 runtime fallback error_type=%s",type(exc).__name__)
        audit=AIDeltaAudit.objects.create(
            conversation_id=conversation_id,message_id=message_id,lead=lead,
            schema_version=31,state_version=snapshot.state_version,mode=mode,
            status=AIDeltaAudit.STATUS_FALLBACK,fallback_used=True,
            question_targets=_safe(list(context.question_targets)),
            canonical_state_before=_audit_state(snapshot),
            rejection_reasons=["provider_or_schema_failure"],
            error_type=type(exc).__name__[:100],
            error_code=str(getattr(exc,"code","") or "")[:100],
            http_status=getattr(exc,"status_code",None))
        return {},audit


def _audit_fields(audit):
    if audit.fallback_used:return {}
    from .delta_contract_v31 import ConversationDeltaV31
    try:return _legacy_fields(ConversationDeltaV31.model_validate(audit.accepted_delta))
    except Exception:return {}
