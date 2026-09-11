"""Webhooks salientes hacia el socio + idempotencia. Envío síncrono best-effort
(no hay cola de workers en el proyecto todavía) — un fallo acá nunca debe
romper el flujo del envío."""
import hashlib
import hmac
import json
import logging

import requests
from django.conf import settings
from django.utils import timezone

from .models import IdempotencyRecord, WebhookDelivery

logger = logging.getLogger(__name__)

_TIMEOUT = getattr(settings, "AI_REQUEST_TIMEOUT_SECONDS", 10)


def firmar(secreto, cuerpo_bytes):
    return hmac.new((secreto or "").encode(), cuerpo_bytes, hashlib.sha256).hexdigest()


def notificar(socio, evento, payload):
    """Registra y envía un webhook al socio. No lanza — cualquier error queda
    en el registro de la entrega."""
    entrega = WebhookDelivery.objects.create(socio=socio, evento=evento, payload=payload)
    if not socio.webhook_url:
        entrega.estado = WebhookDelivery.ESTADO_FALLIDO
        entrega.ultimo_error = "El socio no configuró webhook_url."
        entrega.save(update_fields=["estado", "ultimo_error"])
        return entrega

    cuerpo = json.dumps({"event": evento, "data": payload}).encode()
    firma = firmar(socio.webhook_secret, cuerpo)
    try:
        r = requests.post(
            socio.webhook_url, data=cuerpo,
            headers={"Content-Type": "application/json", "X-Signature": firma},
            timeout=_TIMEOUT,
        )
        entrega.intentos = 1
        entrega.ultimo_codigo = r.status_code
        if 200 <= r.status_code < 300:
            entrega.estado = WebhookDelivery.ESTADO_ENTREGADO
            entrega.entregado_en = timezone.now()
        else:
            entrega.estado = WebhookDelivery.ESTADO_FALLIDO
            entrega.ultimo_error = f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        entrega.intentos = 1
        entrega.estado = WebhookDelivery.ESTADO_FALLIDO
        entrega.ultimo_error = str(e)[:300]
        logger.warning("Webhook a %s (%s) falló: %s", socio.nombre, evento, e)
    entrega.save()
    return entrega


def notificar_envio(envio, evento):
    """Envuelve `notificar` para un Envio: nunca deja que un fallo de webhook
    rompa el flujo (asignar, entregar, etc.)."""
    if not getattr(envio, "socio_id", None):
        return None
    try:
        return notificar(envio.socio, evento, {
            "shipmentCode": envio.codigo,
            "externalRef": envio.external_ref or None,
            "state": envio.estado,
            "stateLabel": envio.get_estado_display(),
        })
    except Exception:  # noqa: BLE001
        logger.exception("notificar_envio falló para %s", envio.codigo)
        return None


def con_idempotencia(socio, key, endpoint, fn):
    """Si ya existe una respuesta guardada para (socio, key, endpoint), la
    devuelve tal cual. Si no, ejecuta `fn()` (debe devolver (status, body)) y
    la guarda. `fn` corre dentro de esta función para poder registrar el
    resultado incluso si falla el guardado (no al revés)."""
    if key:
        previo = IdempotencyRecord.objects.filter(socio=socio, key=key, endpoint=endpoint).first()
        if previo:
            return previo.response_status, previo.response_body, True
    status, body = fn()
    if key:
        IdempotencyRecord.objects.get_or_create(
            socio=socio, key=key, endpoint=endpoint,
            defaults={"response_status": status, "response_body": body},
        )
    return status, body, False
