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
    next_status: str | None = None  # For state transitions (e.g., QUOTED → RESERVATION)


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
        commercial_price: float | None = None,
        conversation_id=None,
        message_id=None,
    ) -> TurnResult:
        missing_before = required_missing(state)
        if not bot_allowed:
            return TurnResult(state, None, ready_to_quote(state), missing_before, 0, suppressed=True)

        logger.info(
            "bot_v4_process_turn_start conversation_id=%s commercial_status=%s price=%s message=%s",
            conversation_id, commercial_status, commercial_price, customer_message[:30] if customer_message else "",
        )

        # RESERVATION mode: Recopilar datos para crear reserva
        from ..models import BotConversationState
        if commercial_status == BotConversationState.STATUS_RESERVATION:
            return self._handle_reservation_response(
                state=state,
                customer_message=customer_message,
                conversation_id=conversation_id,
                commercial_price=commercial_price,
                missing_before=missing_before,
            )

        # QUOTED mode pre-check: Fast path for simple QUOTED questions (no LLM)
        # ORDER MATTERS: Check in this order to avoid false triggers
        if (commercial_status == BotConversationState.STATUS_QUOTED
            and commercial_price is not None
            and commercial_price > 0):
            normalized = customer_message.strip().lower()

            # 1. EMBALAJE PRIMERO - Preguntas sobre servicios → derivar sin LLM (NO transiciona)
            if any(word in normalized for word in ["embalaje", "protección", "proteccion", "seguro", "adicional", "extra", "especial"]):
                logger.info(
                    "bot_v4_quoted_service_question_precheck conversation_id=%s "
                    "message=%s handoff_requested=True (NO transition)",
                    conversation_id, customer_message[:50],
                )
                reply = "El embalaje se cotiza por separado. ¿Te gustaría que te conecte con un asesor para cotizarlo junto con tu mudanza?"
                return TurnResult(
                    state=state,
                    reply=reply,
                    ready_to_quote=True,
                    required_missing=missing_before,
                    llm_calls=0,
                    handoff_requested=True,
                    suppressed=False,
                    conversation_action=ConversationAction.QUESTION,
                )

            # 2. PRECIO - Pregunta sobre precio → responde (NO transiciona)
            if any(word in normalized for word in ["precio", "costo", "cuánto", "cuanto"]):
                logger.info(
                    "bot_v4_quoted_price_question_precheck conversation_id=%s price=%s (NO transition)",
                    conversation_id, commercial_price,
                )
                reply = f"El presupuesto sale en S/ {commercial_price:.2f}. ¿Te late así o querés cambiar algo?"
                return TurnResult(
                    state=state,
                    reply=reply,
                    ready_to_quote=True,
                    required_missing=missing_before,
                    llm_calls=0,
                    handoff_requested=False,
                    suppressed=False,
                    conversation_action=ConversationAction.ACK,
                )

            # 3. CONFIRMACIÓN - SOLO aquí se transiciona a RESERVATION
            if any(word in normalized for word in ["si", "ok", "perfecto", "listo", "adelante", "bueno", "dale", "ya", "registra", "quiero"]):
                logger.info(
                    "bot_v4_quoted_confirmation_precheck conversation_id=%s TRANSITIONING TO RESERVATION",
                    conversation_id,
                )
                reply = "Perfecto. Necesito algunos datos para registrar tu reserva: ¿Cuál es tu nombre completo?"
                return TurnResult(
                    state=state.copy(),
                    reply=reply,
                    ready_to_quote=True,
                    required_missing=missing_before,
                    llm_calls=0,
                    handoff_requested=False,
                    suppressed=False,
                    conversation_action=ConversationAction.CONTINUE,
                    next_status=BotConversationState.STATUS_RESERVATION,
                )

        # COLLECTING mode: normal extraction (also applies to QUOTED if client attempts CORRECTION)
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
        output = self._guard_access_hallucination(output, customer_message, conversation_id, message_id)

        # QUOTED mode optimization: If simple Q&A (no updates/corrections) AND default action AND valid price, return price reply directly
        # Only apply when: status=QUOTED, price>0, action is CONTINUE (not QUESTION/CORRECTION/NEW_QUOTE)
        from ..models import BotConversationState
        logger.info(
            "bot_v4_quoted_check conversation_id=%s is_quoted=%s has_price=%s action=%s message=%s",
            conversation_id,
            commercial_status == BotConversationState.STATUS_QUOTED,
            commercial_price and commercial_price > 0,
            output.conversation_action.value if output.conversation_action else None,
            customer_message[:30] if customer_message else "",
        )
        if (commercial_status == BotConversationState.STATUS_QUOTED
            and commercial_price is not None
            and commercial_price > 0
            and output.conversation_action == ConversationAction.CONTINUE):
            logger.info(
                "bot_v4_mode_quoted_optimization_candidate conversation_id=%s price=%s "
                "action=%s updates_empty=%s corrections_empty=%s",
                conversation_id, commercial_price,
                output.conversation_action.value,
                not output.updates.explicit_values(),
                not output.corrections.explicit_values(),
            )
            updates_empty = not output.updates.explicit_values()
            corrections_empty = not output.corrections.explicit_values()
            if updates_empty and corrections_empty:
                logger.debug(
                    "bot_v4_quoted_simple_qa conversation_id=%s no updates/corrections, using direct price reply",
                    conversation_id,
                )
                quoted_reply = self._handle_quoted_response(
                    state=state,
                    customer_message=customer_message,
                    price=commercial_price,
                    missing_before=missing_before,
                    conversation_id=conversation_id,
                )
                # If _handle_quoted_response returned a valid reply, use it
                if quoted_reply.reply is not None:
                    return quoted_reply
                # Otherwise (invalid price), fall through to normal extraction below

        # RE-EXTRACCIÓN EN NEW_QUOTE: Si el modelo detectó NEW_QUOTE,
        # descartar esa extracción y re-llamar con contexto limpio
        # para evitar contaminar con datos de la solicitud anterior
        if output.conversation_action == ConversationAction.NEW_QUOTE:
            logger.debug(
                "bot_v4_new_quote_reextraction conversation_id=%s message_id=%s "
                "reextracting with empty context to avoid historical data contamination",
                conversation_id, message_id,
            )
            # Segunda llamada con contexto limpio
            clean_context = {
                "goal": context["goal"],
                "current_state": BotState().to_dict(),
                "required_missing": [
                    "origin_district", "destination_district", "origin_floor",
                    "destination_floor", "items",
                ],
                "recent_conversation": [],
                "last_bot_message": "",
                "business_context": context["business_context"],
                "customer_message": customer_message,
                "commercial_status": commercial_status,
            }
            raw_output_clean = self.agent.respond(clean_context)
            logger.debug(
                "bot_v4_new_quote_reextraction_output conversation_id=%s message_id=%s "
                "original_output=%s clean_output=%s",
                conversation_id, message_id, raw_output, raw_output_clean,
            )
            output = self._guard_new_quote(raw_output_clean, commercial_status)

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

            if output.conversation_action == ConversationAction.NEW_QUOTE:
                logger.debug(
                    "bot_v4_new_quote_clean conversation_id=%s message_id=%s "
                    "repair: state resets to empty, will apply ONLY current message data",
                    conversation_id, message_id,
                )

            try:
                # FRONTERA DE SOLICITUD: En NEW_QUOTE repair, descartar updates Y corrections
                repair_output = output
                if output.conversation_action == ConversationAction.NEW_QUOTE:
                    from ..ai.schemas import StatePatch
                    repair_output = output.model_copy(
                        update={"updates": StatePatch(), "corrections": StatePatch()}
                    )
                merged = self._validate_extraction(merge_base, repair_output)
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
            output = self._validate_response(merged, missing_after, output)
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
                output = self._validate_response(merged, missing_after, output)
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

    def _handle_quoted_response(
        self,
        state: BotState,
        customer_message: str,
        price: float | None,
        missing_before: list[str],
        conversation_id=None,
    ) -> TurnResult:
        """
        QUOTED mode: Reply with price, no extraction, no LLM call.
        """
        logger.info(
            "bot_v4_entered_quoted_mode conversation_id=%s price=%s message_snippet=%s",
            conversation_id, price, customer_message[:50],
        )
        # GUARD: If price is missing or invalid, suppress (webhook won't send)
        if price is None or price <= 0:
            logger.warning(
                "bot_v4_quoted_invalid_price conversation_id=%s price=%s "
                "cannot reply with price, suppressing turn to allow fallback handling",
                conversation_id, price,
            )
            # Suppress turn so webhook returns early and doesn't send message
            return TurnResult(
                state=state,
                reply=None,
                ready_to_quote=False,
                required_missing=missing_before,
                llm_calls=0,
                handoff_requested=False,
                suppressed=True,  # Webhook will skip sending
                conversation_action=ConversationAction.QUESTION,
            )

        normalized = customer_message.strip().lower()

        # Price question
        if any(word in normalized for word in ["precio", "costo", "cuánto", "cuanto"]):
            reply = f"El presupuesto sale en S/ {price:.2f}. ¿Te late así o querés cambiar algo?"
        # Confirmation → Transition to RESERVATION
        elif any(word in normalized for word in ["si", "ok", "perfecto", "listo", "adelante", "bueno", "dale", "ya"]):
            logger.debug(
                "bot_v4_quoted_confirmation conversation_id=%s transitioning to RESERVATION",
                conversation_id,
            )
            from ..models import BotConversationState
            reply = "Perfecto. Necesito algunos datos para registrar tu reserva: ¿Cuál es tu nombre completo?"
            return TurnResult(
                state=state.copy(),
                reply=reply,
                ready_to_quote=True,
                required_missing=missing_before,
                llm_calls=0,
                handoff_requested=False,
                suppressed=False,
                conversation_action=ConversationAction.CONTINUE,
                next_status=BotConversationState.STATUS_RESERVATION,  # Signal webhook to transition
            )
        # Question about additional services (embalaje, protección, etc) → handoff to advisor
        elif any(word in normalized for word in ["embalaje", "protección", "proteccion", "seguro", "incluye", "adicional", "extra", "especial"]):
            reply = "El embalaje se cotiza por separado. ¿Te gustaría que te conecte con un asesor para cotizarlo junto con tu mudanza?"
            logger.debug(
                "bot_v4_quoted_service_question conversation_id=%s packing_modalidad=%s handoff_requested=True",
                conversation_id, state.packing_modalidad,
            )
            return TurnResult(
                state=state,  # Preserves packing_modalidad if provided
                reply=reply,
                ready_to_quote=True,
                required_missing=missing_before,
                llm_calls=0,
                handoff_requested=True,  # DERIVE TO ADVISOR
                suppressed=False,
                conversation_action=ConversationAction.QUESTION,
            )
        # Default: NUNCA repetir precio como fallback
        else:
            logger.info(
                "bot_v4_quoted_unclear conversation_id=%s message=%s (unclear intent)",
                conversation_id, customer_message[:50],
            )
            reply = "No te entendí bien. ¿Querés preguntar sobre embalaje, protección, o tienes otra pregunta sobre el servicio?"
            return TurnResult(
                state=state,
                reply=reply,
                ready_to_quote=True,
                required_missing=missing_before,
                llm_calls=0,
                handoff_requested=False,
                suppressed=False,
                conversation_action=ConversationAction.QUESTION,
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
    def _validate_response(merged: BotState, missing: list[str], output: AgentOutput) -> AgentOutput:
        logical_groups = (
            {"origin_district", "destination_district"},
            {"origin_floor", "destination_floor"},
            {"origin_access", "destination_access"},
            {"items"},
        )
        requested = set(output.requested_fields)

        # REGLA DE ORO: nunca degradar reply válido por mezcla de campos
        # PRIMERO: recortar si hay mezcla de grupos lógicos
        if requested and not any(requested <= group for group in logical_groups):
            # Prioridad: ruta > pisos > accesos > items
            trimmed = None
            for group in logical_groups:
                if requested & group:
                    trimmed = [field for field in group if field in requested]
                    break
            if trimmed:
                logger.debug(
                    "bot_v4_requested_fields_trimmed original=%s trimmed=%s",
                    output.requested_fields, trimmed,
                )
                # Retornar output con requested_fields recortado
                return output.model_copy(update={"requested_fields": trimmed})

        # DESPUÉS de trim: verificar que requested_fields estén en missing
        invalid_requests = set(output.requested_fields) - set(missing)
        if invalid_requests:
            logger.debug(
                "bot_v4_response_validation_error invalid_requests type=inconsistent "
                "requested_fields=%s missing=%s invalid=%s",
                output.requested_fields, missing, sorted(invalid_requests),
            )
            raise DomainValidationError(f"requested_fields inconsistentes: {sorted(invalid_requests)}")

        if not missing and "?" in output.reply and not output.customer_question.asked and output.requested_fields:
            logger.debug(
                "bot_v4_response_validation_error invalid_requests type=premature_question "
                "missing=%s reply=%s",
                missing, output.reply[:80],
            )
            raise DomainValidationError("No preguntar más requisitos cuando estado está listo")

        return output

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
        fallback_phrases = {
            "origin_district": "¿De qué distrito a qué distrito sería la mudanza?",
            "destination_district": "¿A qué distrito necesitas ir?",
            "origin_floor": "¿De qué piso sale y a qué piso llega?",
            "destination_floor": "¿A qué piso llegas?",
            "origin_access": "¿Es por ascensor o por escaleras en el origen?",
            "destination_access": "¿Es por ascensor o por escaleras en el destino?",
            "items": "¿Qué cosas vas a mover?",
        }
        if missing:
            field = missing[0]
            reply = fallback_phrases.get(field, f"¿Me das más info sobre {field}?")
            return output.model_copy(update={
                "reply": reply,
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

    @staticmethod
    def _guard_access_hallucination(output: AgentOutput, customer_message: str, conversation_id=None, message_id=None) -> AgentOutput:
        access_keywords = {'ascensor', 'escalera', 'elevador', 'gradas', 'escaleras'}
        msg_lower = customer_message.lower()
        has_access_mention = any(kw in msg_lower for kw in access_keywords)

        if has_access_mention:
            return output

        hallucinated = False
        updates_dict = output.updates.model_dump()

        if output.updates.origin_access and output.updates.origin_access != 'NOT_APPLICABLE':
            updates_dict['origin_access'] = None
            hallucinated = True
        if output.updates.destination_access and output.updates.destination_access != 'NOT_APPLICABLE':
            updates_dict['destination_access'] = None
            hallucinated = True

        if hallucinated:
            logger.warning(
                "bot_v4_access_hallucination conversation_id=%s message_id=%s "
                "removed_origin_access=%s removed_destination_access=%s "
                "message_has_no_access_keywords",
                conversation_id, message_id,
                output.updates.origin_access, output.updates.destination_access,
            )
            from ..ai.schemas import StatePatch
            return output.model_copy(update={"updates": StatePatch(**updates_dict)})

        return output

    def _handle_reservation_response(
        self,
        state: BotState,
        customer_message: str,
        conversation_id=None,
        commercial_price=None,
        missing_before=None,
    ) -> TurnResult:
        """
        RESERVATION mode: Recopilar datos + detectar intención con LLM.
        Cliente puede: responder campo, hacer NEW_QUOTE, preguntar, o cancelar.
        """
        from ..models import BotConversationState

        logger.info(
            "bot_v4_entered_reservation_mode conversation_id=%s message_snippet=%s",
            conversation_id, customer_message[:50],
        )

        try:
            bot_state_record = BotConversationState.objects.filter(
                conversation_key__contains=str(conversation_id)
            ).first()
            if not bot_state_record:
                bot_state_record = BotConversationState.objects.get(id=conversation_id)
        except BotConversationState.DoesNotExist:
            logger.warning("bot_v4_reservation_state_not_found conversation_id=%s", conversation_id)
            return TurnResult(
                state=state, reply="Hubo un error. Por favor, intenta de nuevo.",
                ready_to_quote=True, required_missing=missing_before or [],
                llm_calls=0, handoff_requested=False, suppressed=True,
                conversation_action=ConversationAction.CONTINUE,
            )

        reservation_data = bot_state_record.reservation_data or {}
        missing_fields = self._missing_reservation_fields(reservation_data)

        # Usar LLM para clasificar intención
        next_field = missing_fields[0] if missing_fields else None
        intent_context = {
            "status": "reservation",
            "current_question": self._prompt_for_field(next_field) if next_field else None,
            "customer_message": customer_message,
            "goal": "Clasificar intención del cliente",
        }

        intent_output = self.agent.respond(intent_context)
        llm_calls = 1

        # Determinar intención
        intent = self._classify_reservation_intent(intent_output, customer_message)
        logger.info(
            "bot_v4_reservation_intent conversation_id=%s intent=%s message=%s",
            conversation_id, intent, customer_message[:50],
        )

        # Handle CANCEL
        if intent == "cancel":
            logger.info("bot_v4_reservation_cancelled conversation_id=%s", conversation_id)
            return TurnResult(
                state=state.copy(),
                reply="Entendido. Si en el futuro necesitas cotizar, aquí estaré. ¿Hay algo más en lo que pueda ayudarte?",
                ready_to_quote=False,
                required_missing=missing_before or [],
                llm_calls=llm_calls,
                handoff_requested=False,
                suppressed=False,
                conversation_action=ConversationAction.CONTINUE,
            )

        # Handle NEW_QUOTE
        if intent == "new_quote":
            logger.info("bot_v4_reservation_new_quote conversation_id=%s", conversation_id)
            # Volver a COLLECTING
            bot_state_record.status = BotConversationState.STATUS_COLLECTING
            bot_state_record.save(update_fields=['status'])
            return TurnResult(
                state=BotState(),  # Reset state
                reply="Claro, empecemos de cero. ¿De qué distrito a qué distrito necesitas mudarte?",
                ready_to_quote=False,
                required_missing=["origin_district", "destination_district", "origin_floor", "destination_floor", "items"],
                llm_calls=llm_calls,
                handoff_requested=False,
                suppressed=False,
                conversation_action=ConversationAction.CONTINUE,
            )

        # Handle QUESTION (cliente pregunta algo)
        if intent == "question":
            question_topic = self._extract_question_topic(intent_output, customer_message)
            logger.info("bot_v4_reservation_question conversation_id=%s topic=%s", conversation_id, question_topic)
            reply = self._answer_reservation_question(question_topic, commercial_price)
            # Después responder, volver a pedir el campo
            if next_field:
                reply += f" Mientras tanto, {self._prompt_for_field(next_field).lower()}"
            return TurnResult(
                state=state,
                reply=reply,
                ready_to_quote=True,
                required_missing=missing_before or [],
                llm_calls=llm_calls,
                handoff_requested=False,
                suppressed=False,
                conversation_action=ConversationAction.CONTINUE,
            )

        # Handle ANSWER (cliente responde el campo)
        if intent == "answer" and next_field:
            extracted_value = self._extract_field_value(intent_output, customer_message, next_field)
            if extracted_value:
                reservation_data[next_field] = extracted_value
                bot_state_record.reservation_data = reservation_data
                bot_state_record.save()
                logger.debug(
                    "bot_v4_reservation_field_saved conversation_id=%s field=%s value=%s",
                    conversation_id, next_field, extracted_value[:50],
                )
                missing_fields = self._missing_reservation_fields(reservation_data)

        # Verificar si está completo
        if not missing_fields:
            return self._create_reservation(state, conversation_id, bot_state_record, commercial_price)

        # Pedir siguiente campo
        next_field = missing_fields[0] if missing_fields else None
        reply = self._prompt_for_field(next_field) if next_field else "¿Hay algo más?"

        return TurnResult(
            state=state,
            reply=reply,
            ready_to_quote=True,
            required_missing=missing_before or [],
            llm_calls=llm_calls,
            handoff_requested=False,
            suppressed=False,
            conversation_action=ConversationAction.CONTINUE,
        )

    def _missing_reservation_fields(self, reservation_data: dict) -> list[str]:
        """Retorna campos faltantes en orden."""
        required = ["nombre", "dni", "direccion_origen", "direccion_destino", "fecha", "hora"]
        missing = []
        for field in required:
            if not reservation_data.get(field, "").strip():
                missing.append(field)
        return missing

    def _classify_reservation_intent(self, llm_output: dict, customer_message: str) -> str:
        """Clasifica intención: answer, new_quote, question, cancel."""
        message_lower = customer_message.strip().lower()

        # Detección simple de palabras clave
        if any(w in message_lower for w in ["cancelar", "cancel", "no quiero", "ya no", "olvídalo"]):
            return "cancel"
        if any(w in message_lower for w in ["nueva", "otra", "diferente", "cuánto cuesta", "cuanto cuesta"]):
            return "new_quote"
        if any(w in message_lower for w in ["¿", "?", "incluye", "cómo", "cuál", "qué"]):
            return "question"

        # Default: si el mensaje no es una pregunta ni cancela, asumir respuesta
        return "answer"

    def _prompt_for_field(self, field: str) -> str:
        """Retorna prompt para un campo."""
        prompts = {
            "nombre": "¿Cuál es tu nombre completo?",
            "dni": "¿Tu número de DNI?",
            "direccion_origen": "¿Cuál es la dirección exacta de partida? (calle, número, piso)",
            "direccion_destino": "¿Y la dirección exacta de llegada?",
            "fecha": "¿Para qué fecha desearías el servicio?",
            "hora": "¿A qué hora aproximadamente?",
        }
        return prompts.get(field, "¿Qué más necesitas?")

    def _extract_question_topic(self, llm_output: dict, message: str) -> str:
        """Extrae tema de la pregunta: mudanza, embalaje, precio, etc."""
        message_lower = message.lower()
        if "embalaje" in message_lower or "empacar" in message_lower:
            return "embalaje"
        if "precio" in message_lower or "costo" in message_lower or "cuánto" in message_lower:
            return "precio"
        if "mudanza" in message_lower or "servicio" in message_lower:
            return "mudanza"
        return "general"

    def _answer_reservation_question(self, topic: str, commercial_price=None) -> str:
        """Responde preguntas comunes durante RESERVATION."""
        if topic == "embalaje":
            return "El embalaje se cotiza por separado. Un asesor te dará los detalles."
        if topic == "precio":
            if commercial_price:
                return f"Tu presupuesto actual es de S/ {commercial_price:.2f}."
            return "Tu presupuesto se actualizará según los detalles que me proporciones."
        if topic == "mudanza":
            return "Sí, realizamos mudanzas en Lima Metropolitana. Estamos recopilando tus datos para finalizar la cotización."
        return "Entendido. Continuemos con tu reserva."

    def _extract_field_value(self, llm_output: dict, message: str, field: str) -> str:
        """Extrae valor para un campo específico del mensaje."""
        clean_msg = message.strip()
        if not clean_msg:
            return None

        # Para nombre: simplemente el mensaje
        if field == "nombre":
            return clean_msg if len(clean_msg) > 2 else None

        # Para DNI: solo números
        if field == "dni":
            digits = "".join(c for c in clean_msg if c.isdigit())
            return digits if 8 <= len(digits) <= 12 else None

        # Para direcciones: todo el mensaje
        if "direccion" in field:
            return clean_msg if len(clean_msg) > 5 else None

        # Para fecha y hora: todo el mensaje
        if field in ["fecha", "hora"]:
            return clean_msg if len(clean_msg) > 2 else None

        return None

    def _create_reservation(
        self,
        state: BotState,
        conversation_id=None,
        bot_state_record=None,
        commercial_price=None,
    ) -> TurnResult:
        """Crear reserva en CRM cuando todos los datos están completos."""
        from ..models import BotConversationState

        if not bot_state_record:
            logger.error("bot_v4_create_reservation_no_state conversation_id=%s", conversation_id)
            return TurnResult(
                state=state,
                reply="Hubo un error al crear la reserva.",
                ready_to_quote=True,
                required_missing=[],
                llm_calls=0,
                handoff_requested=False,
                suppressed=True,
                conversation_action=ConversationAction.CONTINUE,
            )

        res_data = bot_state_record.reservation_data
        nombre = res_data.get("nombre", "").strip()
        dni = res_data.get("dni", "").strip()
        dir_origen = res_data.get("direccion_origen", "").strip()
        dir_destino = res_data.get("direccion_destino", "").strip()
        fecha = res_data.get("fecha", "").strip()
        hora = res_data.get("hora", "").strip()

        logger.info(
            "bot_v4_reservation_created conversation_id=%s nombre=%s dni=%s fecha=%s hora=%s "
            "precio=%s",
            conversation_id, nombre, dni, fecha, hora, commercial_price,
        )

        # Actualizar estado a CLOSED + guardar precio
        bot_state_record.status = BotConversationState.STATUS_CLOSED if hasattr(
            BotConversationState, 'STATUS_CLOSED'
        ) else 'closed'
        bot_state_record.quote_price = commercial_price
        bot_state_record.save()

        reply = (
            f"Reserva registrada. Tu servicio está confirmado para {fecha} "
            f"a las {hora}. Un asesor se contactará contigo para confirmar los detalles."
        )

        return TurnResult(
            state=state,
            reply=reply,
            ready_to_quote=True,
            required_missing=[],
            llm_calls=0,
            handoff_requested=True,  # Notificar a asesor
            suppressed=False,
            conversation_action=ConversationAction.CONTINUE,
        )
