import uuid
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.whatsapp.models import ConversacionWhatsApp

from ..enums import (
    AuthorType,
    ContentType,
    Direction,
    GenerationStatus,
    OutboxStatus,
    OwnerState,
    Provider,
    Visibility,
)
from ..errors import InvalidTransition
from ..models import (
    BotGeneration,
    ConversationControl,
    ConversationMapping,
    ConversationTransitionAudit,
    IntegrationMessage,
    IntegrationOutboxEvent,
)
from .channel_policy import is_feature_enabled


@dataclass(frozen=True)
class HumanTakeoverResult:
    message: IntegrationMessage
    outbox: IntegrationOutboxEvent | None
    transitioned: bool
    message_created: bool
    outbox_created: bool


@transaction.atomic
def apply_chatwoot_human_takeover(*, mapping_id, payload, account_id, inbox_id, message_id):
    mapping_ref = ConversationMapping.objects.only("conversation_id").get(pk=mapping_id)
    conversation = (
        ConversacionWhatsApp.objects.select_for_update(of=("self",))
        .select_related("lead", "channel")
        .get(pk=mapping_ref.conversation_id)
    )
    control, _ = ConversationControl.objects.get_or_create(conversation=conversation)
    control = ConversationControl.objects.select_for_update().get(pk=control.pk)
    mapping = (
        ConversationMapping.objects.select_related("contact_inbox__inbox__account")
        .get(pk=mapping_id)
    )
    inbox = mapping.contact_inbox.inbox
    if (
        not mapping.active
        or not inbox.active
        or str(inbox.account.account_id) != str(account_id)
        or str(inbox.inbox_id) != str(inbox_id)
        or inbox.channel_id != conversation.channel_id
        or not is_feature_enabled(conversation.channel, "human_takeover")
    ):
        raise InvalidTransition("Chatwoot takeover is outside the authorized sandbox scope.")

    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
    correlation_id = uuid.uuid4()
    message_defaults = {
        "conversation": conversation,
        "channel": conversation.channel,
        "direction": Direction.OUTBOUND,
        "author_type": AuthorType.AGENT,
        "visibility": Visibility.PUBLIC,
        "content_type": ContentType.TEXT,
        "text": str(payload.get("content") or ""),
        "metadata": {
            "source": "chatwoot_webhook",
            "external_sender_id": str(sender.get("id") or ""),
        },
        "idempotency_key": f"message_created:{message_id}",
        "correlation_id": correlation_id,
    }
    try:
        message, message_created = IntegrationMessage.objects.get_or_create(
            provider=Provider.CHATWOOT,
            external_scope=str(account_id),
            external_message_id=str(message_id),
            defaults=message_defaults,
        )
    except IntegrityError:
        message = IntegrationMessage.objects.get(
            provider=Provider.CHATWOOT,
            external_scope=str(account_id),
            external_message_id=str(message_id),
        )
        message_created = False

    transitioned = control.owner_state != OwnerState.AGENT_ACTIVE
    if transitioned:
        before = control.owner_state
        version_before = control.control_version
        control.owner_state = OwnerState.AGENT_ACTIVE
        control.active_advisor = None
        control.control_version += 1
        control.taken_at = timezone.now()
        control.last_reason = "chatwoot_human_takeover"
        control.last_actor = None
        control.last_actor_type = "chatwoot_agent"
        control.last_correlation_id = correlation_id
        control.save()

        conversation.estado_atencion = ConversacionWhatsApp.ATENCION_ASESOR
        conversation.bot_pausado = True
        conversation.responsable = None
        conversation.instruccion_retorno_bot = ""
        conversation.ultima_actividad = timezone.now()
        conversation.save(update_fields=[
            "estado_atencion", "bot_pausado", "responsable",
            "instruccion_retorno_bot", "ultima_actividad", "actualizada_en",
        ])
        if conversation.lead_id:
            lead = conversation.lead.__class__.objects.select_for_update().get(pk=conversation.lead_id)
            lead.atencion_humana = True
            lead.bot_pausado = True
            lead.save(update_fields=["atencion_humana", "bot_pausado"])

        BotGeneration.objects.filter(
            conversation=conversation,
            status__in=[GenerationStatus.PENDING, GenerationStatus.GENERATING, GenerationStatus.READY],
        ).update(
            status=GenerationStatus.CANCELLED,
            cancelled_at=timezone.now(),
            cancel_reason="chatwoot_human_takeover",
        )
        IntegrationOutboxEvent.objects.filter(
            conversation=conversation,
            destination=Provider.META_WHATSAPP,
            status__in=[OutboxStatus.PENDING, OutboxStatus.RETRY],
            logical_message__author_type=AuthorType.BOT,
        ).update(
            status=OutboxStatus.CANCELLED,
            error_code="human_takeover",
            error_summary="Suppressed by Chatwoot human takeover.",
            locked_at=None,
            locked_by="",
        )
        ConversationTransitionAudit.objects.create(
            conversation=conversation,
            from_state=before,
            to_state=OwnerState.AGENT_ACTIVE,
            action="chatwoot_human_takeover",
            actor=None,
            actor_type="chatwoot_agent",
            external_actor_ref=str(sender.get("id") or ""),
            source="chatwoot_webhook",
            version_before=version_before,
            version_after=control.control_version,
            reason="public_human_agent_message",
            idempotency_key=f"chatwoot-takeover:{account_id}:{message_id}",
            correlation_id=correlation_id,
            metadata={"chatwoot_message_id": str(message_id)},
        )

    outbox = None
    outbox_created = False
    if is_feature_enabled(conversation.channel, "agent_outbound"):
        outbox, outbox_created = IntegrationOutboxEvent.objects.get_or_create(
            destination=Provider.META_WHATSAPP,
            destination_scope=str(conversation.channel_id),
            idempotency_key=f"chatwoot-agent-meta:{account_id}:{message_id}",
            defaults={
                "event_type": "send_public_message",
                "logical_message": message,
                "conversation": conversation,
                "safe_payload": {
                    "logical_message_id": str(message.id),
                    "chatwoot_message_id": str(message_id),
                    "control_version": control.control_version,
                },
                "status": OutboxStatus.PENDING,
                "correlation_id": message.correlation_id,
            },
        )
    return HumanTakeoverResult(message, outbox, transitioned, message_created, outbox_created)
