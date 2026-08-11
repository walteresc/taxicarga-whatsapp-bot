from dataclasses import dataclass

from apps.integrations.services.bot_context import AUTHOR_LABELS
from apps.whatsapp.models import MensajeWhatsApp

from .delta_snapshot import CanonicalSnapshot


@dataclass(frozen=True)
class DeltaContext:
    payload: dict
    last_bot_question: str
    recent_turn_count: int


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
            "customer_message": customer_message,
            "recent_turns": recent,
        },
        last_bot_question=last_bot,
        recent_turn_count=len(recent),
    )
