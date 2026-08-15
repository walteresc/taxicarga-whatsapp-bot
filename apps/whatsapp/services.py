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
ALLOWED_ATTACHMENT_MIME_TYPES = {
    **ALLOWED_IMAGE_MIME_TYPES,
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def send_whatsapp_message(
    to, body, channel=None, *, author_type=None, conversation_id=None
):
    """Envía un mensaje simple o de plantilla por WhatsApp."""
    import json
    import requests

    if author_type and conversation_id and not _ownership_allows_send(
        author_type=author_type,
        conversation_id=conversation_id,
        channel=channel,
    ):
        logger.warning(
            "WhatsApp send blocked by ownership gate (conversation=%s, author=%s).",
            conversation_id,
            author_type,
        )
        return {"sent": False, "reason": "ownership_gate"}

    is_template = isinstance(body, dict) and body.get("type") == "template"

    phone_number_id = getattr(channel, "phone_number_id", "")
    if not channel or not channel.activo or not settings.WHATSAPP_ACCESS_TOKEN or not phone_number_id:
        logger.info(
            "WhatsApp send omitted (channel_id=%s, recipient=%s).",
            getattr(channel, "id", None), _masked_phone(to),
        )
        return {"sent": False, "reason": "missing_credentials"}

    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{phone_number_id}/messages"
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
        response = requests.post(url, headers=headers, json=payload, timeout=5)
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
            _masked_phone(to),
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


def _ownership_allows_send(*, author_type, conversation_id, channel):
    """Apply canonical ownership to channels enrolled in integration."""
    from apps.integrations.services.channel_policy import integration_enabled
    from apps.integrations.enums import AuthorType, OwnerState
    from apps.integrations.models import ConversationControl
    from apps.whatsapp.models import ConversacionWhatsApp

    if not integration_enabled(channel):
        return True
    try:
        conversation = ConversacionWhatsApp.objects.get(pk=conversation_id)
        control = ConversationControl.objects.get(conversation_id=conversation_id)
    except (ConversacionWhatsApp.DoesNotExist, ConversationControl.DoesNotExist):
        return False
    if author_type == AuthorType.BOT:
        return (
            control.owner_state == OwnerState.BOT_ACTIVE
            and conversation.estado_atencion == ConversacionWhatsApp.ATENCION_BOT
            and not conversation.bot_pausado
        )
    if author_type == AuthorType.AGENT:
        return (
            control.owner_state == OwnerState.AGENT_ACTIVE
            and conversation.estado_atencion == ConversacionWhatsApp.ATENCION_ASESOR
            and conversation.bot_pausado
        )
    return True


def send_whatsapp_template_message(to, *, channel):
    """Envía un mensaje de plantilla 'hello_world' al número dado."""
    if not channel or not channel.activo or not channel.phone_number_id or not settings.WHATSAPP_ACCESS_TOKEN:
        logger.info(
            "WhatsApp template omitted (channel_id=%s, recipient=%s).",
            getattr(channel, "id", None), _masked_phone(to),
        )
        return {"sent": False, "reason": "missing_credentials"}
    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{channel.phone_number_id}/messages"
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
            _masked_phone(to),
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



def _masked_phone(value):
    digits = "".join(char for char in str(value or "") if char.isdigit())
    return f"***{digits[-3:]}" if digits else "unknown"


def download_whatsapp_image(cliente, lead, event):
    return _download_whatsapp_media(
        cliente, lead, event, ALLOWED_IMAGE_MIME_TYPES, MAX_IMAGE_BYTES
    )


def download_whatsapp_media(cliente, lead, event):
    return _download_whatsapp_media(
        cliente, lead, event, ALLOWED_ATTACHMENT_MIME_TYPES, MAX_ATTACHMENT_BYTES
    )


def _download_whatsapp_media(cliente, lead, event, allowed_types, max_bytes):
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
        if mime_type not in allowed_types:
            return {"saved": False, "reason": "unsupported_mime_type"}

        media_response = requests.get(metadata["url"], headers=headers, timeout=30)
        media_response.raise_for_status()
        content = media_response.content
        if not content or len(content) > max_bytes:
            return {"saved": False, "reason": "invalid_size"}

        extension = allowed_types[mime_type]
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
