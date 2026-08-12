from dataclasses import dataclass

from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp


BOOLEAN_FIELDS={"elevator","truck_access","staff_required","packing_required",
                "disassembly_required","assembly_required"}


@dataclass(frozen=True)
class ConversationStrategy:
    action: str
    targets: tuple
    asked_count: int = 0
    deferred: tuple = ()


def select_next_conversation_goal(lead, decision):
    """Choose dialogue action from structured state; never changes readiness."""
    pending=tuple(decision.question_targets)
    if not pending:return ConversationStrategy("complete",())
    primary=_safe_group(pending)
    conversation=ConversacionWhatsApp.objects.filter(lead=lead).order_by("-id").first()
    if not conversation:return ConversationStrategy("ask",primary)
    bot_rows=list(MensajeWhatsApp.objects.filter(
        conversacion=conversation,origen=MensajeWhatsApp.ORIGEN_BOT,
    ).exclude(question_targets=[]).order_by("-id")[:8])
    key=_key(primary)
    asked=sum(_key_from_dicts(row.question_targets)==key for row in bot_rows)
    last_key=_key_from_dicts(bot_rows[0].question_targets) if bot_rows else ()
    unanswered=last_key==key and _last_answer_added_no_data(conversation,bot_rows[0] if bot_rows else None)
    if not unanswered:return ConversationStrategy("ask",primary,asked)
    if asked < 2:return ConversationStrategy("clarify",primary,asked)
    alternate=tuple(target for target in pending if target not in primary)
    if alternate:
        return ConversationStrategy("defer",_safe_group(alternate),0,deferred=primary)
    return ConversationStrategy("final_clarify",primary,asked)


def _safe_group(targets):
    first=targets[0]
    if first.field in BOOLEAN_FIELDS:return (first,)
    return tuple(target for target in targets if target.field==first.field)


def _key(targets):return tuple((item.field,item.ref,item.operation) for item in targets)
def _key_from_dicts(targets):return tuple(
    (item.get("field"),item.get("ref"),item.get("operation","set")) for item in targets or ())


def _last_answer_added_no_data(conversation,bot_row):
    if not bot_row:return False
    inbound=MensajeWhatsApp.objects.filter(
        conversacion=conversation,origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        id__gt=bot_row.id).order_by("id").first()
    if not inbound:return False
    from .models import AIDeltaAudit
    audit=AIDeltaAudit.objects.filter(message_id=inbound.id).first()
    if not audit:return False
    changes=(audit.accepted_delta or {}).get("changes",{})
    return not any(changes.get("lead",{}).values()) and not changes.get("locations",[])
