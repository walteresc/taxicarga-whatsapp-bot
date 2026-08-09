import uuid

from django.db import transaction
from django.utils import timezone

from ..enums import AuthorType, Direction, GenerationStatus, OutboxStatus, OwnerState, Provider, Visibility
from ..errors import InvalidTransition, PrivateMessageBlocked
from apps.whatsapp.models import ConversacionWhatsApp

from ..models import BotGeneration, ConversationControl, IntegrationMessage, IntegrationOutboxEvent


def start_generation(conversation_id, *, request_key, input_message=None, correlation_id=None):
    with transaction.atomic():
        control = ConversationControl.objects.select_for_update().get(conversation_id=conversation_id)
        if control.owner_state != OwnerState.BOT_ACTIVE:
            raise InvalidTransition("Bot cannot generate in current state.", current_version=control.control_version)
        generation, _ = BotGeneration.objects.get_or_create(
            conversation_id=conversation_id,
            request_key=request_key,
            defaults={
                "input_message": input_message,
                "control_version_started": control.control_version,
                "expected_owner_state": OwnerState.BOT_ACTIVE,
                "status": GenerationStatus.GENERATING,
                "correlation_id": correlation_id or uuid.uuid4(),
            },
        )
        return generation


def finalize_generation(generation_id, *, result_text):
    with transaction.atomic():
        generation_ref = BotGeneration.objects.only("conversation_id").get(pk=generation_id)
        ConversacionWhatsApp.objects.select_for_update(of=("self",)).get(
            pk=generation_ref.conversation_id
        )
        control = ConversationControl.objects.select_for_update().get(
            conversation_id=generation_ref.conversation_id
        )
        generation = BotGeneration.objects.select_for_update().select_related("conversation").get(pk=generation_id)
        if generation.status in {GenerationStatus.PUBLISHED, GenerationStatus.CANCELLED, GenerationStatus.FAILED}:
            return generation, None, False
        newer_exists = BotGeneration.objects.filter(
            conversation_id=generation.conversation_id, started_at__gt=generation.started_at,
            status__in=[GenerationStatus.PENDING, GenerationStatus.GENERATING, GenerationStatus.READY, GenerationStatus.PUBLISHED],
        ).exists()
        newer_input_exists = bool(generation.input_message_id) and IntegrationMessage.objects.filter(
            conversation_id=generation.conversation_id,
            direction=Direction.INBOUND,
            visibility=Visibility.PUBLIC,
            received_at__gt=generation.input_message.received_at,
        ).exists()
        valid = (
            control.owner_state == generation.expected_owner_state
            and control.control_version == generation.control_version_started
            and not newer_exists
            and not newer_input_exists
        )
        if not valid:
            generation.status = GenerationStatus.CANCELLED
            generation.cancelled_at = timezone.now()
            generation.cancel_reason = "stale_control_or_newer_generation"
            generation.save(update_fields=["status", "cancelled_at", "cancel_reason"])
            return generation, None, False
        message = IntegrationMessage.objects.create(
            conversation_id=generation.conversation_id,
            provider=Provider.INTERNAL,
            external_scope="internal",
            direction=Direction.OUTBOUND,
            author_type=AuthorType.BOT,
            visibility=Visibility.PUBLIC,
            content_type="text",
            text=result_text,
            idempotency_key=f"bot-generation:{generation.id}",
            correlation_id=generation.correlation_id,
        )
        outbox, _ = IntegrationOutboxEvent.objects.get_or_create(
            destination=Provider.META_WHATSAPP,
            destination_scope=str(generation.conversation.channel_id),
            idempotency_key=f"meta-message:{message.id}",
            defaults={
                "event_type": "send_public_message", "logical_message": message,
                "conversation_id": generation.conversation_id,
                "safe_payload": {"logical_message_id": str(message.id)},
                "status": OutboxStatus.PENDING, "correlation_id": generation.correlation_id,
            },
        )
        generation.status = GenerationStatus.PUBLISHED
        generation.result_text = result_text
        generation.completed_at = timezone.now()
        generation.save(update_fields=["status", "result_text", "completed_at"])
        return generation, outbox, True


def create_public_outbox(message):
    if message.visibility != Visibility.PUBLIC:
        raise PrivateMessageBlocked("Private message cannot create a Meta outbox event.")
    return IntegrationOutboxEvent.objects.get_or_create(
        destination=Provider.META_WHATSAPP,
        destination_scope=str(message.conversation.channel_id),
        idempotency_key=f"meta-message:{message.id}",
        defaults={
            "event_type": "send_public_message", "logical_message": message,
            "conversation": message.conversation,
            "safe_payload": {"logical_message_id": str(message.id)}, "correlation_id": message.correlation_id,
        },
    )
