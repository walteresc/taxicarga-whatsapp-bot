import logging
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.base import ContentFile

from .models import EvidenciaWhatsapp

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def send_whatsapp_message(to, body):
    """Envía un mensaje simple o de plantilla por WhatsApp."""
    import json
    import requests

    is_template = isinstance(body, dict) and body.get("type") == "template"

    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        logger.info("WhatsApp no configurado. Mensaje omitido para %s: %s", to, body)
        return {"sent": False, "reason": "missing_credentials"}

    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    if is_template:
        payload = body
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        status_code = getattr(exc.response, "status_code", None)
        error_code = None
        error_subcode = None
        if exc.response is not None:
            try:
                error = exc.response.json().get("error", {})
                error_code = error.get("code")
                error_subcode = error.get("error_subcode")
            except ValueError:
                pass
        logger.exception(
            "Error enviando mensaje de WhatsApp a %s (HTTP %s, codigo %s, subcodigo %s)",
            to,
            status_code,
            error_code,
            error_subcode,
        )
        return {
            "sent": False,
            "reason": "request_error",
            "status_code": status_code,
            "error_code": error_code,
            "error_subcode": error_subcode,
        }


def send_whatsapp_template_message(to):
    """Envía un mensaje de plantilla 'hello_world' al número dado."""
    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {"code": "en_US"},
        },
    }

    try:
        import requests
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        status_code = getattr(exc.response, "status_code", None)
        error_code = None
        error_subcode = None
        if exc.response is not None:
            try:
                error = exc.response.json().get("error", {})
                error_code = error.get("code")
                error_subcode = error.get("error_subcode")
            except ValueError:
                pass
        logger.exception(
            "Error enviando mensaje de plantilla WhatsApp a %s (HTTP %s, codigo %s, subcodigo %s)",
            to,
            status_code,
            error_code,
            error_subcode,
        )
        return {
            "sent": False,
            "reason": "request_error",
            "status_code": status_code,
            "error_code": error_code,
            "error_subcode": error_subcode,
        }

    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        logger.info("WhatsApp no configurado. Mensaje omitido para %s: %s", to, body)
        return {"sent": False, "reason": "missing_credentials"}

    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        status_code = getattr(exc.response, "status_code", None)
        error_code = None
        error_subcode = None
        if exc.response is not None:
            try:
                error = exc.response.json().get("error", {})
                error_code = error.get("code")
                error_subcode = error.get("error_subcode")
            except ValueError:
                pass
        logger.exception(
            "Error enviando mensaje de WhatsApp a %s (HTTP %s, codigo %s, subcodigo %s)",
            to,
            status_code,
            error_code,
            error_subcode,
        )
        return {
            "sent": False,
            "reason": "request_error",
            "status_code": status_code,
            "error_code": error_code,
            "error_subcode": error_subcode,
        }


def download_whatsapp_image(cliente, lead, event):
    if not settings.WHATSAPP_ACCESS_TOKEN:
        return {"saved": False, "reason": "missing_credentials"}
    if not event.get("media_id"):
        return {"saved": False, "reason": "missing_media_id"}

    existing = EvidenciaWhatsapp.objects.filter(media_id=event["media_id"]).first()
    if existing:
        return {"saved": True, "evidence": existing, "duplicate": True}

    headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"}
    metadata_url = (
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
        f"{event['media_id']}"
    )
    try:
        metadata_response = requests.get(metadata_url, headers=headers, timeout=15)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        mime_type = metadata.get("mime_type") or event.get("mime_type", "")
        if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
            return {"saved": False, "reason": "unsupported_mime_type"}

        media_response = requests.get(metadata["url"], headers=headers, timeout=30)
        media_response.raise_for_status()
        content = media_response.content
        if not content or len(content) > MAX_IMAGE_BYTES:
            return {"saved": False, "reason": "invalid_size"}

        extension = ALLOWED_IMAGE_MIME_TYPES[mime_type]
        filename = f"{event['media_id']}{extension}"
        evidence = EvidenciaWhatsapp(
            cliente=cliente,
            lead=lead,
            media_id=event["media_id"],
            mime_type=mime_type,
            sha256_meta=metadata.get("sha256") or event.get("sha256", ""),
            caption=event.get("caption", ""),
        )
        evidence.archivo.save(
            Path(filename).name,
            ContentFile(content),
            save=False,
        )
        evidence.save()
        return {"saved": True, "evidence": evidence, "duplicate": False}
    except (KeyError, requests.RequestException):
        logger.exception("Error descargando imagen de WhatsApp.")
        return {"saved": False, "reason": "download_error"}
