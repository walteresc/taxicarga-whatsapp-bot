from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.cotizador.models import EnvioCotizacion

from .models import MensajeWhatsApp


STATUS_MAP = {"sent": "enviado", "delivered": "entregado", "read": "leido", "failed": "error"}


def extract_statuses(payload):
    statuses = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            statuses.extend(change.get("value", {}).get("statuses", []))
    return statuses


def apply_status(status):
    meta_id = status.get("id", "")
    mapped = STATUS_MAP.get(status.get("status"))
    if not meta_id or not mapped:
        return False
    timestamp = _timestamp(status.get("timestamp"))
    errors = status.get("errors") or []
    error = errors[0] if errors else {}
    with transaction.atomic():
        envio = EnvioCotizacion.objects.select_for_update().filter(meta_message_id=meta_id).first()
        if envio:
            envio.estado = mapped
            fields = ["estado", "actualizado_en"]
            if mapped == "entregado":
                envio.entregado_en = timestamp
                fields.append("entregado_en")
                cotizacion = envio.revision.cotizacion
                if cotizacion.estado in {"borrador", "enviada"}:
                    cotizacion.estado = "entregada"
                    cotizacion.save(update_fields=["estado", "actualizada_en"])
            elif mapped == "leido":
                envio.leido_en = timestamp
                fields.append("leido_en")
            elif mapped == "error":
                envio.error_codigo = str(error.get("code", "failed"))
                envio.error_detalle = error.get("title") or error.get("message") or "Meta reportó error."
                if envio.intento < envio.max_intentos:
                    envio.proximo_reintento = timezone.now() + timedelta(minutes=5 * (2 ** (envio.intento - 1)))
                fields += ["error_codigo", "error_detalle", "proximo_reintento"]
            envio.save(update_fields=fields)
        mensaje = MensajeWhatsApp.objects.filter(meta_message_id=meta_id).first()
        if mensaje:
            mensaje.estado = mapped
            fields = ["estado"]
            if mapped == "entregado":
                mensaje.entregado_en = timestamp
                fields.append("entregado_en")
            elif mapped == "leido":
                mensaje.leido_en = timestamp
                fields.append("leido_en")
            elif mapped == "error":
                mensaje.error_codigo = str(error.get("code", "failed"))
                mensaje.error_detalle = error.get("title") or error.get("message") or "Meta reportó error."
                fields += ["error_codigo", "error_detalle"]
            mensaje.save(update_fields=fields)
    return bool(envio or mensaje)


def _timestamp(value):
    try:
        return timezone.datetime.fromtimestamp(int(value), tz=timezone.get_current_timezone())
    except (TypeError, ValueError, OSError):
        return timezone.now()
