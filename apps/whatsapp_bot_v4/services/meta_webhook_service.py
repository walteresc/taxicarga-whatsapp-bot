import logging
import time
from dataclasses import dataclass

from django.db import IntegrityError, transaction

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel

from ..adapters.meta import InboundMessage, OutboundMessage
from ..models import V4ChannelRoute
from .persistent_conversation_service import PersistentConversationService

logger = logging.getLogger(__name__)

ALLOWED_NUMBERS = [
    "+51995403320",
]


@dataclass(frozen=True)
class MetaTurnResult:
    status: str
    inbound_message_id: int | None = None
    outbound_message_id: int | None = None
    outbound_wamid: str = ""
    llm_calls: int = 0
    ready_to_quote: bool = False


class MetaWebhookV4Service:
    def __init__(self, *, meta_adapter, persistent_service, chatwoot_adapter):
        self.meta_adapter = meta_adapter
        self.persistent_service: PersistentConversationService = persistent_service
        self.chatwoot_adapter = chatwoot_adapter

    def process_payload(self, payload) -> MetaTurnResult:
        t0_total = time.time()

        inbound = self.meta_adapter.parse_inbound(payload)
        if inbound is None:
            return MetaTurnResult("ignored")

        if ALLOWED_NUMBERS and f"+{inbound.customer_id}" not in ALLOWED_NUMBERS:
            logger.debug(
                "bot_v4_whitelist_reject customer_id=%s not in allowed_numbers=%s",
                inbound.customer_id, ALLOWED_NUMBERS,
            )
            return MetaTurnResult("whitelist_rejected")

        channel = self._resolve_channel(inbound.channel_id)
        if channel is None:
            return MetaTurnResult("ignored_channel")
        cliente, lead, conversation = self._resolve_identity(channel, inbound.customer_id)
        incoming, created = self._persist_inbound(conversation, inbound)
        if not created:
            return MetaTurnResult("duplicate", inbound_message_id=incoming.pk)
        self._safe_project_customer(incoming)

        t1_setup = time.time()
        setup_ms = (t1_setup - t0_total) * 1000

        # Obtener request_boundary_at para filtrar historial
        from ..models import BotConversationState
        bot_state_model = BotConversationState.objects.filter(
            conversation_key=f"whatsapp:{conversation.pk}"
        ).first()
        request_boundary_at = bot_state_model.request_boundary_at if bot_state_model else None

        history, last_bot = self._recent_context(
            conversation,
            exclude_message_id=incoming.pk,
            request_boundary_at=request_boundary_at,
        )

        t2_context = time.time()
        context_ms = (t2_context - t1_setup) * 1000

        persistent_result = self.persistent_service.process_turn(
            conversation_key=f"whatsapp:{conversation.pk}",
            conversation=conversation,
            lead=lead,
            message_id=incoming.pk,
            customer_message=inbound.text,
            recent_conversation=history,
            last_bot_message=last_bot,
        )

        t3_process = time.time()
        process_ms = (t3_process - t2_context) * 1000

        turn = persistent_result.turn
        if turn.suppressed or not turn.reply:
            total_ms = (t3_process - t0_total) * 1000
            logger.info(
                "bot_v4_webhook_latency conversation_id=%s status=suppressed "
                "setup=%0.1fms context=%0.1fms process_turn=%0.1fms total=%0.1fms llm_calls=%d",
                conversation.pk, setup_ms, context_ms, process_ms, total_ms, turn.llm_calls,
            )
            return MetaTurnResult(
                "suppressed",
                inbound_message_id=incoming.pk,
                llm_calls=turn.llm_calls,
                ready_to_quote=turn.ready_to_quote,
            )
        outgoing = MensajeWhatsApp.objects.create(
            conversacion=conversation,
            direccion=MensajeWhatsApp.SALIENTE,
            origen=MensajeWhatsApp.ORIGEN_BOT,
            tipo="texto",
            contenido=turn.reply,
            estado="pendiente",
        )

        t4_db = time.time()
        db_ms = (t4_db - t3_process) * 1000

        send_result = self.meta_adapter.send_text(
            channel,
            OutboundMessage(inbound.customer_id, turn.reply, conversation.pk),
        )

        t5_send = time.time()
        send_ms = (t5_send - t4_db) * 1000

        if send_result.sent:
            outgoing.meta_message_id = send_result.external_message_id
            outgoing.estado = "enviado"
            outgoing.save(update_fields=["meta_message_id", "estado"])
            self._safe_project_bot(outgoing)
            status = "sent"
        else:
            outgoing.estado = "error"
            outgoing.error_codigo = send_result.error_code
            outgoing.error_detalle = send_result.error_message
            outgoing.save(update_fields=["estado", "error_codigo", "error_detalle"])
            status = "send_failed"

        t6_total = time.time()
        total_ms = (t6_total - t0_total) * 1000

        logger.info(
            "bot_v4_webhook_latency conversation_id=%s status=%s "
            "setup=%0.1fms context=%0.1fms process_turn=%0.1fms db=%0.1fms send=%0.1fms total=%0.1fms llm_calls=%d",
            conversation.pk, status,
            setup_ms, context_ms, process_ms, db_ms, send_ms, total_ms, turn.llm_calls,
        )

        return MetaTurnResult(
            status,
            incoming.pk,
            outgoing.pk,
            send_result.external_message_id,
            turn.llm_calls,
            turn.ready_to_quote,
        )

    @staticmethod
    def _resolve_channel(phone_number_id):
        return WhatsAppChannel.objects.filter(
            phone_number_id=phone_number_id,
            activo=True,
            v4_route__enabled=True,
        ).first()

    @staticmethod
    @transaction.atomic
    def _resolve_identity(channel, customer_id):
        cliente, _ = Cliente.objects.get_or_create(telefono=customer_id)
        conversation = (
            ConversacionWhatsApp.objects.select_related("lead")
            .filter(cliente=cliente, channel=channel)
            .exclude(estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA)
            .order_by("-creada_en")
            .first()
        )
        if conversation:
            lead = conversation.lead
            if lead is None:
                lead = Lead.objects.create(cliente=cliente, whatsapp_channel=channel)
                conversation.lead = lead
                conversation.save(update_fields=["lead"])
            return cliente, lead, conversation
        lead = Lead.objects.create(cliente=cliente, whatsapp_channel=channel)
        conversation = ConversacionWhatsApp.objects.create(cliente=cliente, lead=lead, channel=channel)
        return cliente, lead, conversation

    @staticmethod
    def _persist_inbound(conversation, inbound: InboundMessage):
        defaults = {
            "conversacion": conversation,
            "direccion": MensajeWhatsApp.ENTRANTE,
            "origen": MensajeWhatsApp.ORIGEN_CLIENTE,
            "tipo": "texto",
            "contenido": inbound.text,
            "estado": "recibido",
        }
        if inbound.timestamp:
            defaults["fecha_mensaje"] = inbound.timestamp
        try:
            with transaction.atomic():
                return MensajeWhatsApp.objects.get_or_create(
                    meta_message_id=inbound.external_message_id,
                    defaults=defaults,
                )
        except IntegrityError:
            return MensajeWhatsApp.objects.get(meta_message_id=inbound.external_message_id), False

    @staticmethod
    def _recent_context(conversation, *, exclude_message_id, request_boundary_at=None):
        query = (
            conversation.mensajes.exclude(pk=exclude_message_id)
            .filter(origen__in=[MensajeWhatsApp.ORIGEN_CLIENTE, MensajeWhatsApp.ORIGEN_BOT])
        )

        # Filtrar por request_boundary_at: solo mensajes POSTERIORES a la frontera
        if request_boundary_at:
            query = query.filter(fecha_mensaje__gt=request_boundary_at)

        messages = list(
            query.order_by("-fecha_mensaje", "-id")[:10]
        )[::-1]
        history = [
            {
                "role": "customer" if item.origen == MensajeWhatsApp.ORIGEN_CLIENTE else "assistant",
                "content": item.contenido,
            }
            for item in messages
        ]
        last_bot = next((item.contenido for item in reversed(messages) if item.origen == MensajeWhatsApp.ORIGEN_BOT), "")
        return history, last_bot

    def _safe_project_customer(self, message):
        try:
            self.chatwoot_adapter.project_customer_message(message)
        except Exception:
            return None

    def _safe_project_bot(self, message):
        try:
            self.chatwoot_adapter.project_bot_message(message)
        except Exception:
            return None
