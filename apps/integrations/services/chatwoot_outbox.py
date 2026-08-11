from django.db import transaction
from django.utils import timezone

from ..enums import OutboxStatus
from ..models import IntegrationOutboxEvent
from .chatwoot_projection import sync_chatwoot_conversation


def process_chatwoot_message_event(event_id, *, client=None):
    with transaction.atomic():
        event = IntegrationOutboxEvent.objects.select_for_update().get(pk=event_id)
        if event.status == OutboxStatus.SENT:
            return "already_sent"
        event.status = OutboxStatus.SENDING
        event.attempts += 1
        event.save(update_fields=["status", "attempts", "updated_at"])
        conversation_id = event.conversation_id
        message_ids = list(event.safe_payload.get("message_ids") or [])
    try:
        result = sync_chatwoot_conversation(
            conversation_id, message_ids=message_ids, live=True, client=client
        )
        if result.messages_failed:
            raise RuntimeError(result.failure or "chatwoot_message_projection_failed")
    except Exception as exc:
        IntegrationOutboxEvent.objects.filter(pk=event_id).update(
            status=OutboxStatus.RETRY,
            error_code="chatwoot_projection_error",
            error_summary=exc.__class__.__name__[:255],
            locked_at=None,
            locked_by="",
        )
        return "retry"
    IntegrationOutboxEvent.objects.filter(pk=event_id).update(
        status=OutboxStatus.SENT, sent_at=timezone.now(),
        error_code="", error_summary="", locked_at=None, locked_by="",
    )
    return "sent"


def process_chatwoot_inbound_event(event_id, *, client=None):
    """Backward-compatible name for existing inbound callers."""
    return process_chatwoot_message_event(event_id, client=client)
