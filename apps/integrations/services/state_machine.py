import uuid

from django.db import transaction
from django.utils import timezone

from ..enums import GenerationStatus, OutboxStatus, OwnerState, Provider, ResumeMode
from ..errors import ConversationOwned, InvalidTransition, PendingHumanOutbox, VersionConflict
from ..models import (
    BotGeneration,
    ContextCheckpoint,
    ConversationControl,
    ConversationTransitionAudit,
    IntegrationOutboxEvent,
)
from apps.whatsapp.models import ConversacionWhatsApp


def request_agent(conversation_id, *, actor=None, reason, idempotency_key, expected_version=None, correlation_id=None):
    return _transition(
        conversation_id, action="request_agent", allowed={OwnerState.BOT_ACTIVE}, target=OwnerState.WAITING_AGENT,
        actor=actor, reason=reason, idempotency_key=idempotency_key, expected_version=expected_version,
        correlation_id=correlation_id,
    )


def take_conversation(conversation_id, *, actor, idempotency_key, expected_version=None, correlation_id=None):
    _validate_actor(actor)
    with transaction.atomic():
        control = _locked_control(conversation_id)
        repeated = _repeated(control, "take", idempotency_key)
        if repeated:
            return control, repeated, False
        _check_version(control, expected_version)
        if control.owner_state == OwnerState.AGENT_ACTIVE:
            if control.active_advisor_id == actor.id:
                return control, None, False
            raise ConversationOwned("Conversation already has an active advisor.", current_version=control.control_version)
        if control.owner_state not in {OwnerState.BOT_ACTIVE, OwnerState.WAITING_AGENT}:
            raise InvalidTransition("Conversation cannot be taken from current state.", current_version=control.control_version)
        before = control.owner_state
        version_before = control.control_version
        control.owner_state = OwnerState.AGENT_ACTIVE
        control.active_advisor = actor
        control.taken_at = timezone.now()
        control.last_actor = actor
        control.last_actor_type = "user"
        control.last_reason = "advisor_take"
        control.control_version += 1
        control.last_correlation_id = correlation_id or uuid.uuid4()
        control.save()
        _cancel_active_generations(control.conversation_id, "advisor_take")
        audit = _audit(control, before, version_before, "take", actor, "advisor_take", idempotency_key)
        _project_transition(control, audit)
        return control, audit, True


def return_to_bot(
    conversation_id, *, actor=None, idempotency_key, expected_version=None,
    instruction="", resume_mode=ResumeMode.WAIT_FOR_CUSTOMER, correlation_id=None,
    actor_type="user", external_actor_ref="", source="django",
):
    if actor_type == "user":
        _validate_actor(actor)
    if resume_mode not in ResumeMode.values:
        raise InvalidTransition("Invalid resume mode.")
    with transaction.atomic():
        control = _locked_control(conversation_id)
        repeated = _repeated(control, "return_to_bot", idempotency_key)
        if repeated:
            return control, repeated, False
        _check_version(control, expected_version)
        if control.owner_state == OwnerState.BOT_ACTIVE:
            return control, None, False
        if control.owner_state != OwnerState.AGENT_ACTIVE:
            raise InvalidTransition("Conversation is not owned by an advisor.", current_version=control.control_version)
        if actor_type == "user" and control.active_advisor_id != actor.id:
            raise InvalidTransition("Only active advisor can return conversation.", current_version=control.control_version)
        if IntegrationOutboxEvent.objects.filter(
            conversation_id=conversation_id,
            destination=Provider.META_WHATSAPP,
            logical_message__author_type="agent",
            status__in=[OutboxStatus.PENDING, OutboxStatus.RETRY, OutboxStatus.SENDING],
        ).exists():
            raise PendingHumanOutbox(
                "A human message is still pending delivery.",
                current_version=control.control_version,
            )
        before = control.owner_state
        version_before = control.control_version
        now = timezone.now()
        control.owner_state = OwnerState.BOT_ACTIVE
        control.active_advisor = None
        control.returned_at = now
        control.last_actor = actor
        control.last_actor_type = actor_type
        control.last_reason = "return_to_bot"
        control.control_version += 1
        control.last_correlation_id = correlation_id or uuid.uuid4()
        control.save()
        conversation = control.conversation
        conversation.estado_atencion = ConversacionWhatsApp.ATENCION_BOT
        conversation.bot_pausado = False
        conversation.responsable = None
        conversation.instruccion_retorno_bot = instruction
        conversation.ultima_actividad = now
        conversation.save(update_fields=[
            "estado_atencion", "bot_pausado", "responsable",
            "instruccion_retorno_bot", "ultima_actividad", "actualizada_en",
        ])
        if conversation.lead_id:
            lead = conversation.lead.__class__.objects.select_for_update().get(pk=conversation.lead_id)
            lead.atencion_humana = False
            lead.bot_pausado = False
            lead.save(update_fields=["atencion_humana", "bot_pausado"])
        audit = _audit(
            control, before, version_before, "return_to_bot", actor, "return_to_bot", idempotency_key,
            actor_type=actor_type, source=source, external_actor_ref=external_actor_ref,
            metadata={"resume_mode": resume_mode, "instruction_present": bool(instruction)},
        )
        _project_transition(control, audit)
        return control, audit, True


def complete_return(checkpoint_id, *, idempotency_key):
    with transaction.atomic():
        checkpoint = ContextCheckpoint.objects.select_for_update().select_related("conversation").get(pk=checkpoint_id)
        control = _locked_control(checkpoint.conversation_id)
        repeated = _repeated(control, "complete_return", idempotency_key)
        if repeated:
            return control, repeated, False
        if control.owner_state != OwnerState.RETURNING_TO_BOT or control.control_version != checkpoint.control_version:
            raise InvalidTransition("Return checkpoint is stale.", current_version=control.control_version)
        before = control.owner_state
        version_before = control.control_version
        control.owner_state = OwnerState.BOT_ACTIVE
        control.active_advisor = None
        control.returned_at = timezone.now()
        control.last_actor = None
        control.last_actor_type = "system"
        control.last_reason = "context_rebuilt"
        control.control_version += 1
        control.save()
        checkpoint.status = "ready"
        checkpoint.completed_at = timezone.now()
        checkpoint.save(update_fields=["status", "completed_at"])
        audit = _audit(control, before, version_before, "complete_return", None, "context_rebuilt", idempotency_key)
        _project_transition(control, audit)
        return control, audit, True


def close_conversation(conversation_id, *, actor=None, reason, idempotency_key, expected_version=None):
    return _transition(
        conversation_id, action="close", allowed={OwnerState.BOT_ACTIVE, OwnerState.WAITING_AGENT, OwnerState.AGENT_ACTIVE},
        target=OwnerState.CLOSED, actor=actor, reason=reason, idempotency_key=idempotency_key,
        expected_version=expected_version,
    )


def reopen_conversation(conversation_id, *, actor=None, target=OwnerState.BOT_ACTIVE, idempotency_key, expected_version=None):
    if target not in {OwnerState.BOT_ACTIVE, OwnerState.WAITING_AGENT}:
        raise InvalidTransition("Invalid reopen target.")
    return _transition(
        conversation_id, action="reopen", allowed={OwnerState.CLOSED}, target=target, actor=actor,
        reason="reopen", idempotency_key=idempotency_key, expected_version=expected_version,
    )


def _transition(conversation_id, *, action, allowed, target, actor, reason, idempotency_key, expected_version=None, correlation_id=None):
    with transaction.atomic():
        control = _locked_control(conversation_id)
        repeated = _repeated(control, action, idempotency_key)
        if repeated:
            return control, repeated, False
        _check_version(control, expected_version)
        if control.owner_state not in allowed:
            raise InvalidTransition("Invalid conversation transition.", current_version=control.control_version)
        before = control.owner_state
        version_before = control.control_version
        control.owner_state = target
        control.control_version += 1
        control.last_actor = actor
        control.last_actor_type = "user" if actor else "system"
        control.last_reason = reason
        control.last_correlation_id = correlation_id or uuid.uuid4()
        now = timezone.now()
        if target == OwnerState.WAITING_AGENT:
            control.requested_at = now
        if target == OwnerState.CLOSED:
            control.closed_at = now
        if target != OwnerState.AGENT_ACTIVE:
            control.active_advisor = None
        if action == "reopen":
            control.closed_at = None
        control.save()
        if target != OwnerState.BOT_ACTIVE:
            _cancel_active_generations(conversation_id, action)
        audit = _audit(control, before, version_before, action, actor, reason, idempotency_key)
        _project_transition(control, audit)
        return control, audit, True


def _locked_control(conversation_id):
    conversation = (
        ConversacionWhatsApp.objects.select_for_update(of=("self",))
        .select_related("lead")
        .get(pk=conversation_id)
    )
    control, _ = ConversationControl.objects.get_or_create(conversation=conversation)
    return (
        ConversationControl.objects.select_for_update(of=("self",))
        .select_related("conversation__lead")
        .get(pk=control.pk)
    )


def _check_version(control, expected_version):
    if expected_version is not None and control.control_version != expected_version:
        raise VersionConflict("Conversation version changed.", current_version=control.control_version)


def _validate_actor(actor):
    if actor is None or not getattr(actor, "is_active", False):
        raise InvalidTransition("Active authenticated advisor is required.")


def assert_advisor_can_send(conversation_id, actor):
    _validate_actor(actor)
    control = ConversationControl.objects.get(conversation_id=conversation_id)
    if control.owner_state != OwnerState.AGENT_ACTIVE or control.active_advisor_id != actor.id:
        raise InvalidTransition("Only active conversation owner can send publicly.", current_version=control.control_version)
    return control


def _repeated(control, action, idempotency_key):
    return ConversationTransitionAudit.objects.filter(
        conversation_id=control.conversation_id, action=action, idempotency_key=idempotency_key
    ).first()


def _audit(control, before, version_before, action, actor, reason, idempotency_key, *, actor_type=None, source="", external_actor_ref="", metadata=None):
    return ConversationTransitionAudit.objects.create(
        conversation_id=control.conversation_id, from_state=before, to_state=control.owner_state,
        action=action, actor=actor, actor_type=actor_type or ("user" if actor else "system"),
        external_actor_ref=external_actor_ref, source=source,
        version_before=version_before, version_after=control.control_version, reason=reason,
        idempotency_key=idempotency_key, correlation_id=control.last_correlation_id or uuid.uuid4(),
        metadata=metadata or {},
    )


def _cancel_active_generations(conversation_id, reason):
    return BotGeneration.objects.filter(
        conversation_id=conversation_id,
        status__in=[GenerationStatus.PENDING, GenerationStatus.GENERATING, GenerationStatus.READY],
    ).update(status=GenerationStatus.CANCELLED, cancelled_at=timezone.now(), cancel_reason=reason)


def _project_transition(control, audit):
    IntegrationOutboxEvent.objects.get_or_create(
        destination=Provider.CHATWOOT,
        idempotency_key=f"transition:{audit.id}",
        defaults={
            "event_type": "conversation_control_changed",
            "conversation_id": control.conversation_id,
            "safe_payload": {"owner_state": control.owner_state, "control_version": control.control_version},
            "status": OutboxStatus.PENDING,
            "correlation_id": audit.correlation_id,
        },
    )
