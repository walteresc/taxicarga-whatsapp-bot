import uuid
from datetime import timedelta
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.conf import settings
from django.utils import timezone

from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp

from ..enums import AuthorType, Direction, GenerationStatus, OwnerState, Provider, Visibility
from ..models import BotGeneration, ConversationControl, IntegrationMessage


@dataclass(frozen=True)
class InboundAuthorization:
    authorized: bool
    integration_message: IntegrationMessage | None = None
    generation: BotGeneration | None = None


@transaction.atomic
def authorize_inbound_trigger(message_id):
    message_ref = MensajeWhatsApp.objects.only("conversacion_id").get(pk=message_id)
    conversation = ConversacionWhatsApp.objects.select_for_update(of=("self",)).get(
        pk=message_ref.conversacion_id
    )
    control, _ = ConversationControl.objects.get_or_create(conversation=conversation)
    control = ConversationControl.objects.select_for_update().get(pk=control.pk)
    message = MensajeWhatsApp.objects.select_for_update().get(pk=message_id)
    if control.owner_state != OwnerState.BOT_ACTIVE:
        return InboundAuthorization(False)

    external_id = message.meta_message_id or f"local:{message.id}"
    try:
        integration_message, _ = IntegrationMessage.objects.get_or_create(
            provider=Provider.META_WHATSAPP,
            external_scope=str(conversation.channel.phone_number_id),
            external_message_id=external_id,
            defaults={
                "conversation": conversation,
                "channel": conversation.channel,
                "direction": Direction.INBOUND,
                "author_type": AuthorType.CUSTOMER,
                "visibility": Visibility.PUBLIC,
                "content_type": "text",
                "text": message.contenido,
                "idempotency_key": f"inbound:{external_id}",
                "received_at": message.fecha_mensaje,
            },
        )
    except IntegrityError:
        integration_message = IntegrationMessage.objects.get(
            provider=Provider.META_WHATSAPP,
            external_scope=str(conversation.channel.phone_number_id),
            external_message_id=external_id,
        )
    generation, created = BotGeneration.objects.select_for_update().get_or_create(
        conversation=conversation,
        request_key=f"inbound:{external_id}",
        defaults={
            "input_message": integration_message,
            "control_version_started": control.control_version,
            "expected_owner_state": OwnerState.BOT_ACTIVE,
            "status": GenerationStatus.GENERATING,
            "correlation_id": uuid.uuid4(),
        },
    )
    if created:
        return InboundAuthorization(True, integration_message, generation)
    reclaim_before = timezone.now() - timedelta(
        seconds=getattr(settings, "BOT_GENERATION_LEASE_SECONDS", 120)
    )
    retryable = generation.status == GenerationStatus.FAILED or (
        generation.status == GenerationStatus.GENERATING
        and generation.started_at <= reclaim_before
    )
    if retryable:
        generation.status = GenerationStatus.GENERATING
        generation.input_message = integration_message
        generation.control_version_started = control.control_version
        generation.expected_owner_state = OwnerState.BOT_ACTIVE
        generation.started_at = timezone.now()
        generation.completed_at = None
        generation.cancelled_at = None
        generation.cancel_reason = ""
        generation.error_summary = ""
        generation.correlation_id = uuid.uuid4()
        generation.save(update_fields=[
            "status", "input_message", "control_version_started",
            "expected_owner_state", "started_at", "completed_at",
            "cancelled_at", "cancel_reason", "error_summary", "correlation_id",
        ])
        return InboundAuthorization(True, integration_message, generation)
    return InboundAuthorization(False, integration_message, generation)
