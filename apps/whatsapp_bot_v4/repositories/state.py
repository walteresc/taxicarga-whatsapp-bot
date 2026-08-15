from typing import Protocol

from django.db import transaction

from ..domain.requirements import ready_to_quote
from ..domain.state import BotState
from ..models import BotConversationState


class BotStateRepository(Protocol):
    def load(self, conversation_key: str) -> BotState: ...
    def save(self, conversation_key: str, state: BotState) -> BotState: ...
    def reset(self, conversation_key: str) -> BotState: ...
    def get_current(self, conversation_key: str) -> BotState: ...
    def get_commercial(self, conversation_key: str) -> dict: ...
    def start_new_request(self, conversation_key: str) -> BotState: ...


class DjangoBotStateRepository:
    def load(self, conversation_key: str) -> BotState:
        snapshot, created = BotConversationState.objects.get_or_create(
            conversation_key=conversation_key,
            defaults={"state_data": BotState().to_dict()},
        )

        # Si es nueva conversación pero hay mensajes previos, setear frontera
        if created and conversation_key.startswith("whatsapp:"):
            try:
                from apps.whatsapp.models import ConversacionWhatsApp
                conv_id = int(conversation_key.split(":")[1])
                conversation = ConversacionWhatsApp.objects.filter(pk=conv_id).first()
                if conversation and conversation.mensajes.exists():
                    # Hay historial previo: setear frontera para aislarlo
                    from django.utils import timezone
                    snapshot.request_boundary_at = timezone.now()
                    snapshot.save(update_fields=["request_boundary_at"])
            except (ValueError, IndexError, Exception):
                pass

        return BotState.from_dict(snapshot.state_data)

    get_current = load

    @transaction.atomic
    def save(self, conversation_key: str, state: BotState, *, commercial=None) -> BotState:
        snapshot, created = BotConversationState.objects.select_for_update().get_or_create(
            conversation_key=conversation_key,
            defaults={
                "state_data": state.to_dict(),
                "status": commercial["status"] if commercial else self._status(state),
                "quote_input_hash": commercial.get("input_hash", "") if commercial else "",
                "quote_mode": commercial.get("mode", "") if commercial else "",
                "quote_price": commercial.get("price") if commercial else None,
            },
        )
        if not created:
            snapshot.state_data = state.to_dict()
            snapshot.status = commercial["status"] if commercial else self._status(state)
            if commercial:
                snapshot.quote_input_hash = commercial.get("input_hash", "")
                snapshot.quote_mode = commercial.get("mode", "")
                snapshot.quote_price = commercial.get("price")
            snapshot.version += 1
            snapshot.save(update_fields=[
                "state_data", "status", "version", "quote_input_hash",
                "quote_mode", "quote_price", "updated_at",
            ])
        return BotState.from_dict(snapshot.state_data)

    def get_commercial(self, conversation_key: str) -> dict:
        snapshot = BotConversationState.objects.filter(conversation_key=conversation_key).first()
        if snapshot is None:
            return {"status": BotConversationState.STATUS_COLLECTING, "input_hash": "", "mode": "", "price": None}
        return {
            "status": snapshot.status,
            "input_hash": snapshot.quote_input_hash,
            "mode": snapshot.quote_mode,
            "price": snapshot.quote_price,
        }

    def reset(self, conversation_key: str) -> BotState:
        BotConversationState.objects.filter(conversation_key=conversation_key).delete()
        return self.load(conversation_key)

    @transaction.atomic
    def start_new_request(self, conversation_key: str) -> BotState:
        snapshot = BotConversationState.objects.select_for_update().filter(
            conversation_key=conversation_key
        ).first()
        if snapshot is not None:
            suffix = f":request:{snapshot.pk}"
            snapshot.conversation_key = f"{conversation_key[:160-len(suffix)]}{suffix}"
            snapshot.save(update_fields=["conversation_key", "updated_at"])
        return self.load(conversation_key)

    @staticmethod
    def _status(state: BotState) -> str:
        return BotConversationState.STATUS_READY if ready_to_quote(state) else BotConversationState.STATUS_COLLECTING


class InMemoryBotStateRepository:
    def __init__(self):
        self._states = {}
        self._commercial = {}

    def load(self, conversation_key: str) -> BotState:
        return self._states.get(conversation_key, BotState()).copy()

    get_current = load

    def save(self, conversation_key: str, state: BotState, *, commercial=None) -> BotState:
        self._states[conversation_key] = state.copy()
        if commercial:
            self._commercial[conversation_key] = dict(commercial)
        return state.copy()

    def get_commercial(self, conversation_key: str) -> dict:
        return self._commercial.get(conversation_key, {
            "status": BotConversationState.STATUS_COLLECTING,
            "input_hash": "", "mode": "", "price": None,
        }).copy()

    def reset(self, conversation_key: str) -> BotState:
        self._states.pop(conversation_key, None)
        self._commercial.pop(conversation_key, None)
        return BotState()

    def start_new_request(self, conversation_key: str) -> BotState:
        if conversation_key in self._states:
            sequence = sum(key.startswith(f"{conversation_key}:request:") for key in self._states) + 1
            archive_key = f"{conversation_key}:request:{sequence}"
            self._states[archive_key] = self._states[conversation_key]
            self._commercial[archive_key] = self._commercial.get(conversation_key, {}).copy()
        self._states[conversation_key] = BotState()
        self._commercial.pop(conversation_key, None)
        return BotState()
