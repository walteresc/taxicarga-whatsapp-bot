import hashlib
import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from ..enums import InboxStatus, OutboxStatus, Provider, Visibility
from ..errors import IdempotencyConflict, PrivateMessageBlocked
from ..models import IntegrationInboxEvent, IntegrationOutboxEvent
from ..ports import SystemClock


def _now(clock=None):
    return (clock or SystemClock()).now()


def payload_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def register_inbox_event(*, provider, event_type, idempotency_key, safe_payload, **refs):
    digest = payload_hash(safe_payload)
    scope = refs.pop("external_scope", "internal")
    query = {"provider": provider, "external_scope": scope, "idempotency_key": idempotency_key}
    event = IntegrationInboxEvent.objects.filter(**query).first()
    external_event_id = refs.get("external_event_id")
    if event is None and external_event_id:
        event = IntegrationInboxEvent.objects.filter(
            provider=provider, external_scope=scope, external_event_id=external_event_id
        ).first()
    if event:
        if event.payload_hash != digest:
            raise IdempotencyConflict("Inbox key was reused with different payload.")
        return event, False
    try:
        with transaction.atomic():
            return IntegrationInboxEvent.objects.create(
                provider=provider, external_scope=scope, event_type=event_type, idempotency_key=idempotency_key,
                payload_hash=digest, safe_payload=safe_payload, **refs,
            ), True
    except IntegrityError:
        event = IntegrationInboxEvent.objects.filter(**query).first()
        if event is None and external_event_id:
            event = IntegrationInboxEvent.objects.filter(
                provider=provider, external_scope=scope, external_event_id=external_event_id
            ).first()
        if event:
            if event.payload_hash != digest:
                raise IdempotencyConflict("Inbox key was reused with different payload.")
            return event, False
        raise


def claim_inbox_event(event_id, worker_id, *, clock=None):
    with transaction.atomic():
        event = IntegrationInboxEvent.objects.select_for_update().get(pk=event_id)
        now = _now(clock)
        if event.attempts >= event.max_attempts:
            event.status = InboxStatus.DEAD_LETTER
            event.save(update_fields=["status"])
            return None
        if event.status not in {InboxStatus.RECEIVED, InboxStatus.RETRY} or (event.next_retry_at and event.next_retry_at > now):
            return None
        event.status = InboxStatus.PROCESSING
        event.attempts += 1
        event.locked_at = now
        event.locked_by = worker_id
        event.processing_started_at = now
        event.save()
        return event


def mark_inbox_processed(event_id, *, clock=None):
    return IntegrationInboxEvent.objects.filter(pk=event_id).update(
        status=InboxStatus.PROCESSED, processed_at=_now(clock), locked_at=None, locked_by="",
        error_code="", error_summary="",
    )


def fail_inbox(event_id, *, code, summary, permanent=False, retry_at=None, clock=None):
    with transaction.atomic():
        event = IntegrationInboxEvent.objects.select_for_update().get(pk=event_id)
        dead = permanent or event.attempts >= event.max_attempts
        event.status = InboxStatus.DEAD_LETTER if dead else InboxStatus.RETRY
        event.next_retry_at = None if dead else (retry_at or _now(clock) + timedelta(seconds=5))
        event.error_code, event.error_summary, event.locked_at, event.locked_by = code, summary[:255], None, ""
        event.save()
        return 1


def recover_inbox_locks(older_than, *, clock=None):
    return IntegrationInboxEvent.objects.filter(
        status=InboxStatus.PROCESSING, locked_at__lt=older_than
    ).update(status=InboxStatus.RETRY, next_retry_at=_now(clock), locked_at=None, locked_by="")


def create_outbox_event(**data):
    scope = data.setdefault("destination_scope", "internal")
    message = data.get("logical_message")
    if data["destination"] == Provider.META_WHATSAPP and message and message.visibility != Visibility.PUBLIC:
        raise PrivateMessageBlocked("Private message cannot create a Meta outbox event.")
    query = {"destination": data["destination"], "destination_scope": scope, "idempotency_key": data["idempotency_key"]}
    event = IntegrationOutboxEvent.objects.filter(**query).first()
    if event:
        return event, False
    try:
        with transaction.atomic():
            return IntegrationOutboxEvent.objects.create(**data), True
    except IntegrityError:
        event = IntegrationOutboxEvent.objects.filter(**query).first()
        if event:
            return event, False
        raise


def claim_outbox_event(event_id, worker_id, *, clock=None):
    with transaction.atomic():
        event = IntegrationOutboxEvent.objects.select_for_update().get(pk=event_id)
        now = _now(clock)
        if event.attempts >= event.max_attempts:
            event.status = OutboxStatus.DEAD_LETTER
            event.save(update_fields=["status"])
            return None
        if event.status not in {OutboxStatus.PENDING, OutboxStatus.RETRY} or event.available_at > now:
            return None
        event.status = OutboxStatus.SENDING
        event.attempts += 1
        event.locked_at = now
        event.locked_by = worker_id
        event.save()
        return event


def mark_outbox_sent(event_id, external_id="", *, clock=None):
    return IntegrationOutboxEvent.objects.filter(pk=event_id).update(
        status=OutboxStatus.SENT, sent_at=_now(clock), external_id=external_id,
        locked_at=None, locked_by="", error_code="", error_summary="",
    )


def fail_outbox(event_id, *, code, summary, permanent=False, available_at=None, clock=None):
    with transaction.atomic():
        event = IntegrationOutboxEvent.objects.select_for_update().get(pk=event_id)
        dead = permanent or event.attempts >= event.max_attempts
        event.status = OutboxStatus.DEAD_LETTER if dead else OutboxStatus.RETRY
        event.available_at = available_at or _now(clock) + timedelta(seconds=5)
        event.error_code, event.error_summary, event.locked_at, event.locked_by = code, summary[:255], None, ""
        event.save()
        return 1


def recover_outbox_locks(older_than, *, clock=None):
    return IntegrationOutboxEvent.objects.filter(
        status=OutboxStatus.SENDING, locked_at__lt=older_than
    ).update(status=OutboxStatus.RETRY, available_at=_now(clock), locked_at=None, locked_by="")


def requeue_dead_letter(event_id, *, clock=None):
    return IntegrationOutboxEvent.objects.filter(pk=event_id, status=OutboxStatus.DEAD_LETTER).update(
        status=OutboxStatus.RETRY, available_at=_now(clock), locked_at=None, locked_by="",
    )


def requeue_inbox_dead_letter(event_id, *, clock=None):
    return IntegrationInboxEvent.objects.filter(pk=event_id, status=InboxStatus.DEAD_LETTER).update(
        status=InboxStatus.RETRY, next_retry_at=_now(clock), locked_at=None, locked_by="",
    )
