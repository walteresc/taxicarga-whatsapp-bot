from dataclasses import dataclass

from apps.integrations.services.bot_context import AUTHOR_LABELS
from apps.whatsapp.models import MensajeWhatsApp

from .delta_snapshot import CanonicalSnapshot


_FIELD_ALIASES = {
    "distrito": "district", "piso": "floor", "ascensor": "elevator",
    "acceso_camion": "truck_access",
}


def canonical_question_targets(raw_targets, snapshot):
    """Upgrade persisted pre-V3.1 targets at the context boundary."""
    refs = list(snapshot.state.get("locations", {}))
    normalized = []
    for raw in raw_targets or ():
        target = dict(raw)
        target["field"] = _FIELD_ALIASES.get(target.get("field"), target.get("field"))
        ref = target.get("ref")
        if isinstance(ref, str) and ref.startswith("location:"):
            try:
                ref = refs[int(ref.partition(":")[2])]
            except (ValueError, IndexError):
                pass
        target["ref"] = ref
        normalized.append(target)
    return tuple(normalized)


@dataclass(frozen=True)
class DeltaContext:
    payload: dict
    last_bot_question: str
    recent_turn_count: int
    question_targets: tuple[dict, ...] = ()


def build_delta_context(
    conversation_id,
    *,
    trigger_message_id,
    customer_message,
    snapshot: CanonicalSnapshot,
    max_recent_turns=4,
):
    rows = list(
        MensajeWhatsApp.objects.filter(
            conversacion_id=conversation_id,
            id__lt=trigger_message_id,
            origen__in=AUTHOR_LABELS,
            tipo="texto",
        ).exclude(contenido="").order_by("-fecha_mensaje", "-id")[: max_recent_turns + 1]
    )
    last_bot_row = next(
        (row for row in rows if row.origen == MensajeWhatsApp.ORIGEN_BOT),
        None,
    )
    last_bot = last_bot_row.contenido if last_bot_row else ""
    question_targets = canonical_question_targets(
        last_bot_row.question_targets if last_bot_row else (), snapshot)
    recent = [
        {"author": AUTHOR_LABELS[row.origen], "text": row.contenido}
        for row in reversed(rows)
        if row.id != getattr(last_bot_row, "id", None)
        and row.contenido != customer_message
    ]
    recent = recent[-max_recent_turns:]
    return DeltaContext(
        payload={
            "state_version": snapshot.state_version,
            "state": snapshot.state,
            "last_bot_question": last_bot or None,
            "last_question_targets": list(question_targets),
            "customer_message": customer_message,
            "recent_turns": recent,
        },
        last_bot_question=last_bot,
        recent_turn_count=len(recent),
        question_targets=question_targets,
    )
