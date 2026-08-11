import json
import logging
import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.integrations.enums import OutboxStatus, Provider
from apps.integrations.models import IntegrationOutboxEvent
from apps.whatsapp.models import MensajeWhatsApp

from .delta_context import build_delta_context
from .delta_contract_v2 import ConversationDeltaV2, empty_delta_v2
from .delta_snapshot import build_canonical_snapshot
from .delta_validator_v2 import validate_delta_v2
from .models import AIDeltaAudit
from .providers import build_provider


logger = logging.getLogger(__name__)

DELTA_SHADOW_EVENT = "extract_ai_delta_shadow"


DELTA_EXTRACTION_SYSTEM_PROMPT = """
Comprendes mensajes libres de clientes de TaxiCarga. Devuelve EXCLUSIVAMENTE
informacion que el mensaje actual agrega, corrige o aclara. State solo resuelve
referencias: nunca copies ni repitas datos conocidos. Cada valor y cada ref de
ubicacion requieren una cita literal breve del customer_message y evidence_type:
explicit, explicit_contextual o inferred. Contextual usa tambien last_bot_question.
Marca inferred si el cliente no afirmo directamente la conclusion. No conviertas
observaciones en conclusiones: "queda lejos" puede ser access_observation, no
truck_access=false; "una cuadra" no son 100 metros. Django rechazara inferred.
Si una observacion no identifica ubicacion, no elijas origin/destination/both:
devuelvela en ambiguities con possible_refs. Usa both solo con evidencia expresa
de ambos lugares. Tolera typos y lenguaje coloquial. Campos ausentes se conservan.
No decidas precio, readiness, reservas, ownership ni estados comerciales.
""".strip()


def _sanitize_text(value):
    value = re.sub(r"\b\d{8,}\b", "[redacted-number]", str(value or ""))
    value = re.sub(r"[\w.+-]+@[\w.-]+", "[redacted-email]", value)
    return value[:200]


def _sanitize_delta(delta):
    data = delta.model_dump(mode="json", exclude_none=True)
    for location in data.get("changes", {}).get("locations", []):
        values = location.get("set", {})
        if "access_observation" in values:
            values["access_observation"]["value"] = _sanitize_text(
                values["access_observation"]["value"]
            )
            values["access_observation"]["evidence"] = _sanitize_text(
                values["access_observation"]["evidence"]
            )
    lead_values = data.get("changes", {}).get("lead", {})
    if "load" in lead_values:
        lead_values["load"]["value"] = _sanitize_text(lead_values["load"]["value"])
        lead_values["load"]["evidence"] = _sanitize_text(lead_values["load"]["evidence"])
    return data


def _sanitize_legacy_extraction(extracted):
    protected = {
        "cliente_nombre", "dni_reserva", "direccion_origen", "direccion_destino"
    }
    sanitized = {}
    for key, value in (extracted or {}).items():
        if key in protected:
            sanitized[key] = "[redacted]"
        elif value is None or isinstance(value, (bool, int, float)):
            sanitized[key] = value
        else:
            sanitized[key] = _sanitize_text(value)
    return sanitized


def extract_conversation_delta(context, *, provider_name=None):
    provider = build_provider("extraction", provider_name=provider_name)
    result = provider.generate_structured(
        [
            {"role": "system", "content": DELTA_EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(context.payload, ensure_ascii=False, separators=(",", ":")),
            },
        ],
        schema_model=ConversationDeltaV2,
    )
    return ConversationDeltaV2.model_validate_json(result.text), result


def run_delta_shadow(
    *, lead, conversation_id, trigger_message_id, customer_message,
    legacy_extraction=None,
):
    existing = AIDeltaAudit.objects.filter(message_id=trigger_message_id).first()
    if existing:
        return existing
    snapshot = build_canonical_snapshot(lead)
    context = build_delta_context(
        conversation_id,
        trigger_message_id=trigger_message_id,
        customer_message=customer_message,
        snapshot=snapshot,
    )
    try:
        delta, metrics = extract_conversation_delta(context)
        validation = validate_delta_v2(
            delta, snapshot, customer_message=customer_message,
            last_bot_question=context.last_bot_question,
            expected_state_version=snapshot.state_version,
        )
        rejected = [item.path for item in validation.rejected]
        status = AIDeltaAudit.STATUS_REJECTED if rejected else AIDeltaAudit.STATUS_ACCEPTED
        return AIDeltaAudit.objects.create(
            conversation_id=conversation_id,
            message_id=trigger_message_id,
            lead=lead,
            provider=metrics.provider,
            model=metrics.model,
            schema_version=delta.schema_version,
            state_version=snapshot.state_version,
            status=status,
            accepted_delta=_sanitize_delta(validation.accepted),
            legacy_extraction=_sanitize_legacy_extraction(legacy_extraction),
            rejected_fields=rejected,
            rejection_reasons=[item.reason for item in validation.rejected],
            latency_ms=metrics.latency_ms,
            input_tokens=metrics.input_tokens,
            output_tokens=metrics.output_tokens,
        )
    except Exception as exc:
        logger.warning("AI delta shadow fallback error_type=%s", type(exc).__name__)
        return AIDeltaAudit.objects.create(
            conversation_id=conversation_id,
            message_id=trigger_message_id,
            lead=lead,
            schema_version=2,
            state_version=snapshot.state_version,
            status=AIDeltaAudit.STATUS_FALLBACK,
            accepted_delta=_sanitize_delta(empty_delta_v2()),
            legacy_extraction=_sanitize_legacy_extraction(legacy_extraction),
            rejection_reasons=["provider_or_schema_failure"],
            fallback_used=True,
            error_type=type(exc).__name__[:100],
            error_code=str(getattr(exc, "code", "") or "")[:100],
            http_status=getattr(exc, "status_code", None),
            provider=settings.AI_EXTRACTION_PROVIDER,
            model=(
                settings.OPENAI_EXTRACTION_MODEL
                if settings.AI_EXTRACTION_PROVIDER == "openai"
                else settings.DEEPSEEK_EXTRACTION_MODEL
            ),
        )


def queue_delta_shadow(*, trigger_message_id, legacy_extraction=None):
    """Durably queue shadow work without adding IA latency to the webhook."""
    message = MensajeWhatsApp.objects.select_related("conversacion__channel").get(
        pk=trigger_message_id
    )
    return IntegrationOutboxEvent.objects.get_or_create(
        destination=Provider.INTERNAL,
        destination_scope=f"channel:{message.conversacion.channel_id}",
        idempotency_key=f"ai-delta-shadow:{message.id}",
        defaults={
            "event_type": DELTA_SHADOW_EVENT,
            "conversation": message.conversacion,
            "safe_payload": {
                "message_id": message.id,
                "legacy_extraction": _sanitize_legacy_extraction(legacy_extraction),
            },
        },
    )


def process_delta_shadow_event(event_id, *, worker_id="integration"):
    with transaction.atomic():
        event = IntegrationOutboxEvent.objects.select_for_update().get(pk=event_id)
        if event.status == OutboxStatus.SENT:
            return "already_sent"
        if event.destination != Provider.INTERNAL or event.event_type != DELTA_SHADOW_EVENT:
            event.status = OutboxStatus.DEAD_LETTER
            event.error_code = "invalid_internal_event"
            event.save(update_fields=["status", "error_code", "updated_at"])
            return "dead_letter"
        message = MensajeWhatsApp.objects.select_related("conversacion__lead").get(
            pk=event.safe_payload["message_id"]
        )
        if message.conversacion_id != event.conversation_id or message.conversacion.lead_id is None:
            event.status = OutboxStatus.DEAD_LETTER
            event.error_code = "conversation_scope_mismatch"
            event.save(update_fields=["status", "error_code", "updated_at"])
            return "dead_letter"
        event.status = OutboxStatus.SENDING
        event.attempts += 1
        event.locked_by = worker_id
        event.locked_at = timezone.now()
        event.save(update_fields=["status", "attempts", "locked_by", "locked_at", "updated_at"])
    try:
        run_delta_shadow(
            lead=message.conversacion.lead,
            conversation_id=message.conversacion_id,
            trigger_message_id=message.id,
            customer_message=message.contenido,
            legacy_extraction=event.safe_payload.get("legacy_extraction"),
        )
    except Exception as exc:
        IntegrationOutboxEvent.objects.filter(pk=event_id).update(
            status=OutboxStatus.RETRY,
            error_code="delta_shadow_error",
            error_summary=type(exc).__name__[:255],
            locked_at=None,
            locked_by="",
        )
        return "retry"
    IntegrationOutboxEvent.objects.filter(pk=event_id).update(
        status=OutboxStatus.SENT,
        sent_at=timezone.now(),
        error_code="",
        error_summary="",
        locked_at=None,
        locked_by="",
    )
    return "sent"
