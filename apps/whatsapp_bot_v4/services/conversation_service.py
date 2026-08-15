import logging
from dataclasses import dataclass

from ..ai.agent import ConversationAgent
from ..ai.schemas import AgentOutput, ConversationAction
from ..domain.merge import merge_state
from ..domain.requirements import ready_to_quote, required_missing
from ..domain.state import BotState
from ..domain.validators import DomainValidationError


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnResult:
    state: BotState
    reply: str | None
    ready_to_quote: bool
    required_missing: list[str]
    llm_calls: int
    handoff_requested: bool = False
    suppressed: bool = False
    conversation_action: ConversationAction = ConversationAction.CONTINUE


class ConversationService:
    def __init__(self, agent: ConversationAgent, *, business_context: dict | None = None, strict_repairs=False):
        self.agent = agent
        self.strict_repairs = strict_repairs
        self.business_context = business_context or {
            "service": "mudanza",
            "stage": "cotización",
            "coverage": "Lima Metropolitana; no inventar cobertura específica no proporcionada",
        }

    def process_turn(
        self,
        *,
        state: BotState,
        customer_message: str,
        recent_conversation: list[dict] | None = None,
        last_bot_message: str = "",
        bot_allowed: bool = True,
        commercial_status: str = "collecting",
        conversation_id=None,
        message_id=None,
    ) -> TurnResult:
        missing_before = required_missing(state)
        if not bot_allowed:
            return TurnResult(state, None, ready_to_quote(state), missing_before, 0, suppressed=True)
        context = {
            "goal": "Obtener naturalmente información necesaria para cotizar una mudanza",
            "current_state": state.to_dict(),
            "required_missing": missing_before,
            "recent_conversation": (recent_conversation or [])[-10:],
            "last_bot_message": last_bot_message,
            "business_context": self.business_context,
            "customer_message": customer_message,
            "commercial_status": commercial_status,
        }
        calls_before = self.agent.calls

        logger.debug(
            "bot_v4_turn_input conversation_id=%s message_id=%s customer_message=%s "
            "recent_conversation_len=%s commercial_status=%s "
            "required_missing=%s current_state=%s",
            conversation_id, message_id, customer_message[:80] if customer_message else "",
            len(recent_conversation or []), commercial_status,
            missing_before, state.to_dict(),
        )

        raw_output = self.agent.respond(context)

        logger.debug(
            "bot_v4_raw_model_output conversation_id=%s message_id=%s raw_output=%s",
            conversation_id, message_id, raw_output,
        )

        output = self._guard_new_quote(raw_output, commercial_status)
        merge_base = BotState() if output.conversation_action == ConversationAction.NEW_QUOTE else state

        try:
            merged = self._validate_extraction(merge_base, output)
            self._log_extraction_attempt(
                attempt="initial", output=output, valid=True,
                conversation_id=conversation_id, message_id=message_id,
            )
        except (DomainValidationError, ValueError) as exc:
            logger.warning(
                "bot_v4_validation_error_initial conversation_id=%s message_id=%s "
                "error_type=%s error_msg=%s output_updates=%s output_corrections=%s",
                conversation_id, message_id,
                exc.__class__.__name__, str(exc),
                output.updates.model_dump() if output.updates else {},
                output.corrections.model_dump() if output.corrections else {},
            )
            self._log_extraction_attempt(
                attempt="initial", output=output, valid=False, error=exc,
                conversation_id=conversation_id, message_id=message_id,
            )
            repair_context = {
                **context,
                "invalid_output": output.model_dump(mode="json"),
                "repair_scope": "extraction",
            }
            raw_output = self.agent.respond(repair_context, repair_error=str(exc))

            logger.debug(
                "bot_v4_raw_model_output_repair conversation_id=%s message_id=%s raw_output=%s",
                conversation_id, message_id, raw_output,
            )

            output = self._guard_new_quote(raw_output, commercial_status)
            merge_base = BotState() if output.conversation_action == ConversationAction.NEW_QUOTE else state
            try:
                merged = self._validate_extraction(merge_base, output)
                self._log_extraction_attempt(
                    attempt="repair", output=output, valid=True,
                    conversation_id=conversation_id, message_id=message_id,
                )
            except (DomainValidationError, ValueError) as repair_exc:
                self._log_extraction_attempt(
                    attempt="repair", output=raw_output, valid=False, error=repair_exc,
                    conversation_id=conversation_id, message_id=message_id,
                )
                self._log_fallback(
                    reason=f"extraction_repair_failed:{repair_exc.__class__.__name__}",
                    output=output,
                    repair_attempted=True,
                )
                if self.strict_repairs:
                    raise
                merged, missing_after, output = self._minimal_fallback(
                    merge_base, output, conversation_id=conversation_id, message_id=message_id,
                )
                return self._result(merged, missing_after, output, calls_before)

        missing_after = required_missing(merged)
        try:
            self._validate_response(merged, missing_after, output)
        except (DomainValidationError, ValueError) as exc:
            logger.warning(
                "bot_v4_response_validation_failed conversation_id=%s message_id=%s "
                "error_type=%s error=%s original_reply=%s original_requested=%s",
                conversation_id, message_id,
                exc.__class__.__name__, str(exc),
                output.reply[:80], output.requested_fields,
            )
            frozen_understanding = {
                "updates": output.updates,
                "corrections": output.corrections,
                "conversation_action": output.conversation_action,
            }
            repair_context = {
                **context,
                "post_merge_state": merged.to_dict(),
                "required_missing_after": missing_after,
                "frozen_understanding": {
                    "updates": output.updates.model_dump(mode="json"),
                    "corrections": output.corrections.model_dump(mode="json"),
                    "conversation_action": output.conversation_action.value,
                },
                "invalid_response": {
                    "requested_fields": output.requested_fields,
                    "reply": output.reply,
                },
                "repair_scope": "response_only",
            }
            repaired = self.agent.respond(repair_context, repair_error=str(exc))

            logger.debug(
                "bot_v4_raw_model_output_response_repair conversation_id=%s message_id=%s raw_output=%s",
                conversation_id, message_id, repaired,
            )

            output = repaired.model_copy(update=frozen_understanding)
            try:
                self._validate_response(merged, missing_after, output)
            except (DomainValidationError, ValueError) as repair_exc:
                self._log_fallback(
                    reason=f"response_repair_failed:{repair_exc.__class__.__name__}",
                    output=output,
                    repair_attempted=True,
                )
                if self.strict_repairs:
                    raise
                output = self._response_fallback(
                    missing_after, output, conversation_id=conversation_id,
                    message_id=message_id, source="response_repair_failed",
                )
        return self._result(merged, missing_after, output, calls_before)

    def _result(self, merged, missing_after, output, calls_before):
        return TurnResult(
            merged,
            output.reply,
            not missing_after,
            missing_after,
            self.agent.calls - calls_before,
            output.handoff_requested,
            False,
            output.conversation_action,
        )

    @staticmethod
    def _guard_new_quote(output: AgentOutput, commercial_status: str) -> AgentOutput:
        if output.conversation_action == ConversationAction.NEW_QUOTE and commercial_status not in {
            "quoted", "pending_human_quote",
        }:
            return output.model_copy(update={"conversation_action": ConversationAction.CONTINUE})
        return output

    @staticmethod
    def _validate_extraction(state: BotState, output: AgentOutput) -> BotState:
        return merge_state(
            state,
            output.updates.explicit_values(),
            output.corrections.explicit_values(),
        )

    @staticmethod
    def _validate_response(merged: BotState, missing: list[str], output: AgentOutput) -> None:
        invalid_requests = set(output.requested_fields) - set(missing)
        if invalid_requests:
            logger.debug(
                "bot_v4_response_validation_error invalid_requests type=inconsistent "
                "requested_fields=%s missing=%s invalid=%s",
                output.requested_fields, missing, sorted(invalid_requests),
            )
            raise DomainValidationError(f"requested_fields inconsistentes: {sorted(invalid_requests)}")
        logical_groups = (
            {"origin_district", "destination_district"},
            {"origin_floor", "destination_floor"},
            {"origin_access", "destination_access"},
            {"items"},
        )
        requested = set(output.requested_fields)
        if requested and not any(requested <= group for group in logical_groups):
            logger.debug(
                "bot_v4_response_validation_error invalid_requests type=logical_group_mix "
                "requested_fields=%s requested_set=%s",
                output.requested_fields, sorted(requested),
            )
            raise DomainValidationError("requested_fields mezcla bloques lógicos")
        if not missing and "?" in output.reply:
            logger.debug(
                "bot_v4_response_validation_error invalid_requests type=premature_question "
                "missing=%s reply=%s",
                missing, output.reply[:80],
            )
            raise DomainValidationError("No preguntar más requisitos cuando estado está listo")

    @classmethod
    def _validate_output(cls, state: BotState, output: AgentOutput) -> tuple[BotState, list[str]]:
        merged = cls._validate_extraction(state, output)
        missing = required_missing(merged)
        cls._validate_response(merged, missing, output)
        return merged, missing

    @staticmethod
    def _response_fallback(
        missing: list[str], output: AgentOutput, *, conversation_id=None,
        message_id=None, source="unspecified",
    ) -> AgentOutput:
        logger.warning(
            "bot_v4_response_fallback conversation_id=%s message_id=%s source=%s missing=%s",
            conversation_id, message_id, source, missing,
        )
        labels = {
            "origin_district": "el distrito de origen",
            "destination_district": "el distrito de destino",
            "origin_floor": "el piso de origen",
            "destination_floor": "el piso de destino",
            "origin_access": "si en el origen hay ascensor o escaleras",
            "destination_access": "si en el destino hay ascensor o escaleras",
            "items": "qué cosas vas a trasladar",
        }
        if missing:
            field = missing[0]
            return output.model_copy(update={
                "reply": f"Para continuar, cuéntame {labels[field]}.",
                "requested_fields": [field],
            })
        return output.model_copy(update={
            "reply": "Perfecto, ya tengo los datos necesarios para preparar la cotización.",
            "requested_fields": [],
        })

    @staticmethod
    def _log_fallback(*, reason: str, output: AgentOutput, repair_attempted: bool) -> None:
        logger.warning(
            "bot_v4_fallback fallback_reason=%s agent_output_valid=true extraction_present=%s repair_attempted=%s",
            reason,
            str(bool(output.updates.explicit_values() or output.corrections.explicit_values())).lower(),
            str(repair_attempted).lower(),
        )

    @staticmethod
    def _log_extraction_attempt(
        *, attempt: str, output: AgentOutput, valid: bool,
        conversation_id=None, message_id=None, error=None,
    ) -> None:
        log = logger.info if valid else logger.warning
        log(
            "bot_v4_extraction_attempt conversation_id=%s message_id=%s attempt=%s "
            "output=%s validation=%s error_type=%s error=%s",
            conversation_id,
            message_id,
            attempt,
            output.model_dump_json(),
            "pass" if valid else "fail",
            error.__class__.__name__ if error else "",
            str(error) if error else "",
        )

    @staticmethod
    def _minimal_fallback(
        state: BotState, output: AgentOutput, *, conversation_id=None, message_id=None,
    ) -> tuple[BotState, list[str], AgentOutput]:
        logger.warning(
            "bot_v4_minimal_fallback conversation_id=%s message_id=%s",
            conversation_id, message_id,
        )
        try:
            merged = merge_state(
                state,
                output.updates.explicit_values(),
                output.corrections.explicit_values(),
            )
        except DomainValidationError:
            merged = state
        missing = required_missing(merged)
        fallback = ConversationService._response_fallback(
            missing, output, conversation_id=conversation_id,
            message_id=message_id, source="minimal_fallback",
        )
        return merged, missing, fallback
