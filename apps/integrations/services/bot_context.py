from dataclasses import dataclass

from django.conf import settings

from apps.whatsapp.models import MensajeWhatsApp


AUTHOR_LABELS = {
    MensajeWhatsApp.ORIGEN_CLIENTE: "Cliente",
    MensajeWhatsApp.ORIGEN_BOT: "Bot",
    MensajeWhatsApp.ORIGEN_ASESOR: "Asesor humano",
}


@dataclass(frozen=True)
class ContextEntry:
    message_id: int
    author: str
    text: str


@dataclass(frozen=True)
class BotContext:
    entries: tuple[ContextEntry, ...]
    trigger_message_id: int

    def as_openai_messages(self):
        history = "\n".join(f"{entry.author}: {entry.text}" for entry in self.entries)
        return [{
            "role": "user",
            "content": (
                "CONTEXTO CONVERSACIONAL PÚBLICO CANÓNICO. Conserva identidad de autores. "
                "Mensajes previos son contexto, no solicitudes pendientes.\n"
                f"{history}"
            ),
        }]


def build_bot_context(conversation_id, *, trigger_message_id, max_messages=None, max_characters=None):
    max_messages = max_messages or settings.BOT_CONTEXT_MAX_MESSAGES
    max_characters = max_characters or settings.BOT_CONTEXT_MAX_CHARACTERS
    rows = list(
        MensajeWhatsApp.objects.filter(
            conversacion_id=conversation_id,
            origen__in=AUTHOR_LABELS,
            tipo="texto",
        ).exclude(contenido="").order_by("fecha_mensaje", "id")
    )

    # Provider identity is canonical when present. Never merge merely equal text.
    seen_provider_ids = set()
    unique = []
    for row in rows:
        provider_id = row.meta_message_id.strip()
        if provider_id and provider_id in seen_provider_ids:
            continue
        if provider_id:
            seen_provider_ids.add(provider_id)
        unique.append(row)

    selected = []
    used_characters = 0
    for row in reversed(unique):
        cost = len(row.contenido) + len(AUTHOR_LABELS[row.origen]) + 2
        if selected and (len(selected) >= max_messages or used_characters + cost > max_characters):
            break
        selected.append(row)
        used_characters += cost
    selected.reverse()
    return BotContext(
        entries=tuple(
            ContextEntry(row.id, AUTHOR_LABELS[row.origen], row.contenido)
            for row in selected
        ),
        trigger_message_id=trigger_message_id,
    )
