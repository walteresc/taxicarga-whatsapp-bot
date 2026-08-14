from dataclasses import dataclass

from django.db import IntegrityError, transaction

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel

from ..adapters.meta import InboundMessage, OutboundMessage
from ..models import V4ChannelRoute
from .persistent_conversation_service import PersistentConversationService


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
        inbound = self.meta_adapter.parse_inbound(payload)
        if inbound is None:
            return MetaTurnResult("ignored")
        channel = self._resolve_channel(inbound.channel_id)
        if channel is None:
            return MetaTurnResult("ignored_channel")
        cliente, lead, conversation = self._resolve_identity(channel, inbound.customer_id)
        incoming, created = self._persist_inbound(conversation, inbound)
        if not created:
            return MetaTurnResult("duplicate", inbound_message_id=incoming.pk)
        self._safe_project_customer(incoming)
        history, last_bot = self._recent_context(conversation, exclude_message_id=incoming.pk)
        persistent_result = self.persistent_service.process_turn(
            conversation_key=f"whatsapp:{conversation.pk}",
            conversation=conversation,
            lead=lead,
            message_id=incoming.pk,
            customer_message=inbound.text,
            recent_conversation=history,
            last_bot_message=last_bot,
        )
        turn = persistent_result.turn
        if turn.suppressed or not turn.reply:
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
        send_result = self.meta_adapter.send_text(
            channel,
            OutboundMessage(inbound.customer_id, turn.reply, conversation.pk),
        )
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
    def _recent_context(conversation, *, exclude_message_id):
        messages = list(
            conversation.mensajes.exclude(pk=exclude_message_id)
            .filter(origen__in=[MensajeWhatsApp.ORIGEN_CLIENTE, MensajeWhatsApp.ORIGEN_BOT])
            .order_by("-fecha_mensaje", "-id")[:10]
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
