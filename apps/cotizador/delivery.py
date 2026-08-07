from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.whatsapp.services import send_whatsapp_message

from .commercial import marcar_revision_enviada
from .models import EnvioCotizacion, RevisionCotizacion


def enviar_revision_whatsapp(revision_id):
    with transaction.atomic():
        revision = RevisionCotizacion.objects.select_for_update().select_related(
            "cotizacion__lead__cliente", "cotizacion__channel"
        ).get(pk=revision_id)
        if not revision.mensaje_whatsapp.strip():
            raise ValidationError("La revisión no tiene mensaje para WhatsApp.")
        previo = revision.envios.order_by("-intento").first()
        intento = (previo.intento if previo else 0) + 1
        if previo and intento > previo.max_intentos:
            raise ValidationError("Se alcanzó el máximo de reintentos.")
        envio = EnvioCotizacion.objects.create(
            revision=revision,
            channel=revision.cotizacion.channel,
            intento=intento,
            max_intentos=previo.max_intentos if previo else 3,
        )

    result = send_whatsapp_message(
        revision.cotizacion.lead.cliente.telefono,
        revision.mensaje_whatsapp,
        channel=revision.cotizacion.channel,
    )
    message_id = _message_id(result)
    if message_id:
        envio.meta_message_id = message_id
        envio.estado = "enviado"
        envio.proximo_reintento = None
        envio.save(update_fields=["meta_message_id", "estado", "proximo_reintento", "actualizado_en"])
        marcar_revision_enviada(revision)
    else:
        envio.estado = "error"
        envio.error_codigo = str(result.get("error_code") or result.get("status_code") or "send_error")
        envio.error_detalle = result.get("reason") or "Meta no aceptó el mensaje."
        if envio.intento < envio.max_intentos:
            envio.proximo_reintento = timezone.now() + timedelta(minutes=5 * (2 ** (envio.intento - 1)))
        envio.save(update_fields=["estado", "error_codigo", "error_detalle", "proximo_reintento", "actualizado_en"])
    return envio


def reintentar_envios_vencidos(limit=50):
    ids = list(
        EnvioCotizacion.objects.filter(
            estado="error", proximo_reintento__lte=timezone.now(), intento__lt=models.F("max_intentos")
        ).order_by("proximo_reintento").values_list("revision_id", flat=True)[:limit]
    )
    return [enviar_revision_whatsapp(revision_id) for revision_id in ids]


def _message_id(result):
    if not isinstance(result, dict):
        return ""
    messages = result.get("messages") or []
    return messages[0].get("id", "") if messages else ""
