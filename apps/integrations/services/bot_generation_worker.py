from contextlib import nullcontext

from django.db import connection, transaction
from django.utils import timezone

from apps.ia.conversation_engine import handle_incoming_message, next_question_targets_for
from apps.leads.models import Lead
from apps.whatsapp.models import MensajeWhatsApp

from ..enums import OutboxStatus, Provider
from ..models import BotGeneration, IntegrationOutboxEvent
from .bot_context import build_bot_context
from .generations import fail_generation, finalize_generation


BOT_GENERATION_EVENT="process_bot_generation"


def _lead_state_guard():
    """Serialize a turn in PostgreSQL without holding a SQLite read lock.

    The turn includes a provider call.  A long SQLite transaction cannot be
    upgraded to a writer after another connection (for example Chatwoot)
    commits, and fails with ``database is locked``.  Production PostgreSQL
    keeps the row-level serialization guarantee.
    """
    return transaction.atomic() if connection.vendor == "postgresql" else nullcontext()


def _lead_for_generation(lead_id):
    queryset = Lead.objects.select_related("cliente")
    if connection.vendor == "postgresql":
        queryset = queryset.select_for_update()
    return queryset.get(pk=lead_id)


def queue_bot_generation(*,message_id,generation_id):
    message=MensajeWhatsApp.objects.select_related("conversacion__channel").get(pk=message_id)
    return IntegrationOutboxEvent.objects.get_or_create(
        destination=Provider.INTERNAL,destination_scope=f"channel:{message.conversacion.channel_id}",
        idempotency_key=f"bot-generation-work:{generation_id}",defaults={
            "event_type":BOT_GENERATION_EVENT,"conversation":message.conversacion,
            "safe_payload":{"message_id":message.id,"generation_id":str(generation_id)}})


def process_bot_generation_event(event_id,*,worker_id="integration"):
    with transaction.atomic():
        event=IntegrationOutboxEvent.objects.select_for_update().get(pk=event_id)
        if event.status == OutboxStatus.SENT:return "already_sent"
        if event.destination != Provider.INTERNAL or event.event_type != BOT_GENERATION_EVENT:
            event.status=OutboxStatus.DEAD_LETTER;event.error_code="invalid_internal_event"
            event.save(update_fields=["status","error_code","updated_at"]);return "dead_letter"
        message=MensajeWhatsApp.objects.select_related(
            "conversacion__lead__cliente","conversacion__channel").get(
                pk=event.safe_payload["message_id"])
        generation=BotGeneration.objects.get(pk=event.safe_payload["generation_id"])
        if generation.conversation_id != message.conversacion_id:
            event.status=OutboxStatus.DEAD_LETTER;event.error_code="conversation_scope_mismatch"
            event.save(update_fields=["status","error_code","updated_at"]);return "dead_letter"
        event.status=OutboxStatus.SENDING;event.attempts+=1
        event.locked_by=worker_id;event.locked_at=timezone.now()
        event.save(update_fields=["status","attempts","locked_by","locked_at","updated_at"])
    try:
        with _lead_state_guard():
            lead=_lead_for_generation(message.conversacion.lead_id)
            context=build_bot_context(message.conversacion_id,trigger_message_id=message.id)
            reply=handle_incoming_message(lead.cliente,message.contenido,
                                          canonical_context=context,generation_id=generation.id)
            lead.refresh_from_db()
            generation.refresh_from_db(fields=["asked_targets"])
            targets=(generation.asked_targets or next_question_targets_for(lead))
        _generation,_outbox,published=finalize_generation(
            generation.id,result_text=reply,question_targets=targets)
    except Exception as exc:
        fail_generation(generation.id,exc)
        IntegrationOutboxEvent.objects.filter(pk=event_id).update(
            status=OutboxStatus.RETRY,error_code="bot_generation_error",
            error_summary=type(exc).__name__[:255],locked_at=None,locked_by="")
        return "retry"
    IntegrationOutboxEvent.objects.filter(pk=event_id).update(
        status=OutboxStatus.SENT,sent_at=timezone.now(),error_code="",error_summary="",
        locked_at=None,locked_by="")
    return "published" if published else "cancelled"
