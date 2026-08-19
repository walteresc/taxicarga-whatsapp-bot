import logging
from dataclasses import dataclass

from django.db import transaction

from ..ai.schemas import ConversationAction
from ..domain.requirements import ready_to_quote, required_missing
from ..domain.state import BotState
from ..models import BotConversationState
from .conversation_service import ConversationService, TurnResult
from .quote_bridge import quote_input_hash, quote_reply


logger = logging.getLogger(__name__)


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

        # Check ConversationOwnership: does bot have control?
        bot_allowed = True
        if conversation is not None:
            from ..models import ConversationOwnership
            ownership, _ = ConversationOwnership.objects.get_or_create(conversation=conversation)

            # Fallback: sync with Chatwoot adapter for backward compatibility in tests
            # Chatwoot is source of truth when available; ConversationOwnership fallback for CRM-only mode
            if self.chatwoot_adapter is not None:
                chatwoot_allowed = self.chatwoot_adapter.is_bot_allowed(conversation)
                # Sync both directions: Chatwoot ↔ ConversationOwnership
                if not chatwoot_allowed:
                    # Chatwoot says advisor, ensure ownership reflects it
                    if ownership.owner_type != ConversationOwnership.OWNER_ADVISOR:
                        ownership.owner_type = ConversationOwnership.OWNER_ADVISOR
                        ownership.control_mode = ConversationOwnership.MODE_MANUAL
                        ownership.save(update_fields=['owner_type', 'control_mode'])
                else:
                    # Chatwoot says bot allowed, ensure ownership reflects it
                    if ownership.owner_type != ConversationOwnership.OWNER_BOT:
                        ownership.owner_type = ConversationOwnership.OWNER_BOT
                        ownership.save(update_fields=['owner_type'])

            bot_allowed = ownership.is_bot_allowed()
            logger.debug(
                "conversation_ownership check conversation_id=%s owner_type=%s control_mode=%s bot_allowed=%s",
                conversation.pk, ownership.owner_type, ownership.control_mode, bot_allowed,
            )

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
        # Cargar el modelo para chequear si hay frontera
        bot_state_model = BotConversationState.objects.filter(conversation_key=conversation_key).first()
        if bot_state_model and bot_state_model.request_boundary_at and contexto_conversation:
            # Si tenemos frontera, vaciar recent_conversation
            # (el modelo solo verá el turno actual, no el historial previo)
            contexto_conversation = []

        logger.debug(
            "persistent_before_process_turn conversation_key=%s commercial_status=%s price=%s message=%s",
            conversation_key, commercial.get("status"), commercial.get("price"), customer_message[:50],
        )
        turn = self.conversation_service.process_turn(
            state=state,
            customer_message=customer_message,
            recent_conversation=contexto_conversation,
            last_bot_message=last_bot_message,
            commercial_status=commercial["status"],
            commercial_price=commercial.get("price"),
            conversation_id=getattr(conversation, "pk", None),
            message_id=message_id,
        )
        if turn.conversation_action == ConversationAction.NEW_QUOTE:
            if conversation is None or self.crm_adapter is None:
                raise ValueError("NEW_QUOTE requiere conversación y CRM adapter")
            with transaction.atomic():
                lead = self.crm_adapter.start_new_request(conversation)
                self.repository.start_new_request(conversation_key)
                # FRONTERA: Marcar dónde cortar recent_conversation para siguientes turnos
                # Persistir en columna propia de BotConversationState, no en state_data
                from django.utils import timezone
                bot_state = BotConversationState.objects.get(conversation_key=conversation_key)
                bot_state.request_boundary_at = timezone.now()
                bot_state.save(update_fields=['request_boundary_at'])
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

        # Handle state transitions (e.g., QUOTED → RESERVATION)
        if turn.next_status and turn.next_status != commercial.get("status"):
            logger.info(
                "bot_v4_state_transition conversation_key=%s from=%s to=%s",
                conversation_key, commercial.get("status"), turn.next_status,
            )
            bot_state = BotConversationState.objects.get(conversation_key=conversation_key)
            bot_state.status = turn.next_status
            bot_state.save(update_fields=['status'])

        # Fallback price injection: If QUOTED and reply has no price number, inject the known price
        # BUT: Never inject if handoff_requested (bot is deriving to advisor, not closing quote)
        if (turn.reply and commercial.get("status") == BotConversationState.STATUS_QUOTED
                and not turn.handoff_requested):
            has_price_number = any(char.isdigit() for char in turn.reply)
            if not has_price_number and commercial.get("price"):
                logger.info(
                    "bot_v4_price_fallback_injection status=%s quote_price=%s reply_snippet=%s",
                    commercial.get("status"), commercial.get("price"), turn.reply[:80],
                )
                price_msg = f"Perfecto. Con los datos que me diste, el servicio tiene un costo de S/ {commercial['price']:.2f}."
                turn = TurnResult(
                    turn.state, price_msg, turn.ready_to_quote, turn.required_missing, turn.llm_calls,
                    turn.handoff_requested, turn.suppressed, turn.conversation_action, turn.next_status,
                )

        return PersistentTurnResult(turn, crm_result, decision)
