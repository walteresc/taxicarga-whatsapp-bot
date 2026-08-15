from dataclasses import dataclass

from django.db import transaction

from ..ai.schemas import ConversationAction
from ..domain.requirements import ready_to_quote, required_missing
from ..models import BotConversationState
from .conversation_service import ConversationService, TurnResult
from .quote_bridge import quote_input_hash, quote_reply


@dataclass(frozen=True)
class PersistentTurnResult:
    turn: TurnResult
    crm_result: object | None = None
    quote_decision: object | None = None


class PersistentConversationService:
    ACKNOWLEDGEMENTS = {"ok", "okay", "gracias", "perfecto", "listo", "esta bien", "está bien"}

    def __init__(self, conversation_service, repository, *, crm_adapter=None, chatwoot_adapter=None, quote_bridge=None):
        self.conversation_service: ConversationService = conversation_service
        self.repository = repository
        self.crm_adapter = crm_adapter
        self.chatwoot_adapter = chatwoot_adapter
        self.quote_bridge = quote_bridge

    def process_turn(
        self,
        *,
        conversation_key: str,
        customer_message: str,
        conversation=None,
        lead=None,
        message_id=None,
        recent_conversation=None,
        last_bot_message="",
    ) -> PersistentTurnResult:
        state = self.repository.load(conversation_key)
        commercial = self.repository.get_commercial(conversation_key)
        bot_allowed = True
        if conversation is not None and self.chatwoot_adapter is not None:
            bot_allowed = self.chatwoot_adapter.is_bot_allowed(conversation)
        if not bot_allowed:
            turn = TurnResult(state, None, ready_to_quote(state), required_missing(state), 0, suppressed=True)
            return PersistentTurnResult(turn)
        normalized = customer_message.strip().lower().strip(".!¡¿? ")
        if (
            self.quote_bridge is not None
            and commercial["status"] in {
                BotConversationState.STATUS_QUOTED,
                BotConversationState.STATUS_PENDING_HUMAN,
            }
            and normalized in self.ACKNOWLEDGEMENTS
        ):
            return PersistentTurnResult(TurnResult(
                state, "Perfecto 👍", True, [], 0,
                conversation_action=ConversationAction.ACK,
            ))
        # FRONTERA DE SOLICITUD: Si hay NEW_QUOTE anterior, no mostrar
        # al modelo mensajes antes de esa frontera
        contexto_conversation = recent_conversation
        if state.request_boundary_at and contexto_conversation:
            # Si tenemos frontera, vaciar recent_conversation
            # (el modelo solo vera el turno actual, no el historial previo)
            contexto_conversation = []

        turn = self.conversation_service.process_turn(
            state=state,
            customer_message=customer_message,
            recent_conversation=contexto_conversation,
            last_bot_message=last_bot_message,
            commercial_status=commercial["status"],
            conversation_id=getattr(conversation, "pk", None),
            message_id=message_id,
        )
        if turn.conversation_action == ConversationAction.NEW_QUOTE:
            if conversation is None or self.crm_adapter is None:
                raise ValueError("NEW_QUOTE requiere conversación y CRM adapter")
            # FRONTERA: Marcar dónde cortar recent_conversation para siguientes turnos
            from datetime import datetime
            turn.state.request_boundary_at = datetime.utcnow().isoformat()
            with transaction.atomic():
                lead = self.crm_adapter.start_new_request(conversation)
                self.repository.start_new_request(conversation_key)
            commercial = self.repository.get_commercial(conversation_key)
            if self.chatwoot_adapter:
                try:
                    self.chatwoot_adapter.project_commercial_status(conversation)
                except Exception:
                    pass
        current_input_hash = quote_input_hash(turn.state) if turn.ready_to_quote else ""
        same_commercial_revision = bool(
            current_input_hash and commercial.get("input_hash") == current_input_hash
        )
        crm_result = (
            self.crm_adapter.sync(turn.state, lead)
            if self.crm_adapter and lead and not same_commercial_revision
            else None
        )
        decision = None
        if (
            self.quote_bridge is not None
            and conversation is not None
            and lead is not None
            and turn.ready_to_quote
            and not same_commercial_revision
        ):
            decision = self.quote_bridge.evaluate(
                state=turn.state,
                lead=lead,
                conversation=conversation,
                request_id=getattr(crm_result, "request_id", None),
            )
            if self.crm_adapter:
                self.crm_adapter.apply_quote_decision(decision, lead, conversation)
            if self.chatwoot_adapter:
                try:
                    self.chatwoot_adapter.project_commercial_status(conversation)
                except Exception:
                    pass
            turn = TurnResult(
                turn.state, quote_reply(decision), True, [], turn.llm_calls,
                turn.handoff_requested, turn.suppressed, turn.conversation_action,
            )
            self.repository.save(conversation_key, turn.state, commercial=decision.commercial_data())
        else:
            persisted_commercial = commercial if turn.ready_to_quote and commercial.get("input_hash") else None
            self.repository.save(conversation_key, turn.state, commercial=persisted_commercial)
        return PersistentTurnResult(turn, crm_result, decision)
