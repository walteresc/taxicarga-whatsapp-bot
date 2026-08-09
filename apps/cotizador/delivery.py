import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.integrations.enums import (
    AuthorType, Direction, OutboxStatus, OwnerState, Provider, Visibility,
)
from apps.integrations.models import (
    ConversationControl, IntegrationMessage, IntegrationOutboxEvent,
)
from apps.integrations.services.state_machine import take_conversation
from apps.whatsapp.models import ConversacionWhatsApp

from .commercial import marcar_revision_enviada
from .models import EnvioCotizacion, RevisionCotizacion


def queue_revision_whatsapp(revision_id, *, actor=None):
    """Create exactly one logical WhatsApp delivery for a concrete revision."""
    revision_ref = RevisionCotizacion.objects.select_related(
        "cotizacion__solicitud__conversacion", "cotizacion__lead"
    ).get(pk=revision_id)
    conversation = _conversation_for(revision_ref)
    if actor is not None:
        take_conversation(
            conversation.id,
            actor=actor,
            idempotency_key=f"commercial-send-takeover:{revision_id}",
        )

    with transaction.atomic():
        conversation = ConversacionWhatsApp.objects.select_for_update(of=("self",)).get(pk=conversation.id)
        control = ConversationControl.objects.select_for_update().get(conversation=conversation)
        revision = RevisionCotizacion.objects.select_for_update().select_related("cotizacion").get(pk=revision_id)
        if not revision.mensaje_whatsapp.strip():
            raise ValidationError("La revisión no tiene mensaje para WhatsApp.")
        author_type = AuthorType.AGENT if actor is not None else AuthorType.BOT
        expected = OwnerState.AGENT_ACTIVE if actor is not None else OwnerState.BOT_ACTIVE
        if control.owner_state != expected:
            raise ValidationError("Ownership incompatible con el envío comercial.")
        if revision.enviada:
            envio = revision.envios.filter(estado__in=["enviado", "entregado", "leido"]).first()
            if envio:
                return envio, False

        correlation_id = uuid.uuid4()
        message, _ = IntegrationMessage.objects.get_or_create(
            provider=Provider.INTERNAL,
            external_scope="commercial",
            idempotency_key=f"quote-revision:{revision.id}:whatsapp",
            defaults={
                "conversation": conversation,
                "channel": conversation.channel,
                "direction": Direction.OUTBOUND,
                "author_type": author_type,
                "visibility": Visibility.PUBLIC,
                "text": revision.mensaje_whatsapp,
                "metadata": {
                    "quote_revision_id": revision.id,
                    "control_version": control.control_version,
                },
                "correlation_id": correlation_id,
            },
        )
        outbox, created = IntegrationOutboxEvent.objects.get_or_create(
            destination=Provider.META_WHATSAPP,
            destination_scope=str(conversation.channel_id),
            idempotency_key=f"quote-revision:{revision.id}:whatsapp",
            defaults={
                "event_type": "send_commercial_quote",
                "logical_message": message,
                "conversation": conversation,
                "safe_payload": {
                    "logical_message_id": str(message.id),
                    "quote_revision_id": revision.id,
                    "control_version": control.control_version,
                },
                "status": OutboxStatus.PENDING,
                "correlation_id": correlation_id,
            },
        )
        envio, _ = EnvioCotizacion.objects.get_or_create(
            revision=revision,
            outbox_event=outbox,
            defaults={"channel": conversation.channel, "estado": "pendiente"},
        )
        return envio, created


def enviar_revision_whatsapp(revision_id, *, actor=None):
    """Compatibility entry point: queue; workers perform the real HTTP."""
    return queue_revision_whatsapp(revision_id, actor=actor)[0]


def mark_commercial_outbox_sent(event_id, provider_message_id):
    with transaction.atomic():
        envio = EnvioCotizacion.objects.select_for_update().select_related("revision").filter(
            outbox_event_id=event_id
        ).first()
        if not envio:
            return None
        envio.estado = "enviado"
        envio.meta_message_id = provider_message_id
        envio.proximo_reintento = None
        envio.save(update_fields=["estado", "meta_message_id", "proximo_reintento", "actualizado_en"])
        marcar_revision_enviada(envio.revision)
        return envio


def mark_commercial_outbox_failed(event_id, code, detail, retrying):
    EnvioCotizacion.objects.filter(outbox_event_id=event_id).update(
        estado="error", error_codigo=code, error_detalle=detail[:255],
        proximo_reintento=timezone.now() if retrying else None,
    )


def reintentar_envios_vencidos(limit=50):
    """Retries are claimed from IntegrationOutboxEvent; no new logical send is created."""
    return list(IntegrationOutboxEvent.objects.filter(
        envio_cotizacion__estado="error",
        status=OutboxStatus.RETRY,
        available_at__lte=timezone.now(),
    ).order_by("available_at").values_list("id", flat=True)[:limit])


def _conversation_for(revision):
    conversation = getattr(getattr(revision.cotizacion, "solicitud", None), "conversacion", None)
    if not conversation:
        conversation = ConversacionWhatsApp.objects.filter(lead=revision.cotizacion.lead).exclude(
            estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA
        ).order_by("-ultima_actividad").first()
    if not conversation:
        raise ValidationError("La cotización no tiene conversación canónica activa.")
    return conversation
