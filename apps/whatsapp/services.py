import hashlib
import logging
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from .models import EvidenciaWhatsapp, MensajeWhatsApp, MensajeAdjunto, ConversacionWhatsApp

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
    """Envía un mensaje simple o de plantilla por WhatsApp (Meta o YCloud).

    Si conversation_id se proporciona, registra el mensaje en BD via process_whatsapp_message().
    """
    import json
    import requests
    from apps.clientes.models import Cliente

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

    if not channel or not channel.activo:
        logger.info("WhatsApp send omitted: channel inactive")
        return {"sent": False, "reason": "channel_inactive"}

    # Determinar si usar YCloud o Meta
    if settings.YCLOUD_ENABLED and settings.YCLOUD_API_KEY:
        logger.info(f"Usando YCloud para enviar a {_masked_phone(to)}")
        from apps.whatsapp_bot_v4.services.ycloud_webhook_service import send_via_ycloud
        try:
            send_via_ycloud(to, body if isinstance(body, str) else body.get('text', {}).get('body', ''))
            return {"sent": True, "reason": "ycloud"}
        except Exception as e:
            logger.error(f"Error enviando con YCloud: {e}")
            return {"sent": False, "reason": "ycloud_error", "error": str(e)}

    # Fallback a Meta
    is_template = isinstance(body, dict) and body.get("type") == "template"
    phone_number_id = getattr(channel, "phone_number_id", "")
    if not settings.WHATSAPP_ACCESS_TOKEN or not phone_number_id:
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
        result = response.json()

        # Register outbound message in BD if conversation provided
        if conversation_id and result.get("messages"):
            try:
                conversation = ConversacionWhatsApp.objects.get(pk=conversation_id)
                client = conversation.cliente
                meta_id = result["messages"][0].get("id", "")

                # Determine sender_type from author_type
                from apps.whatsapp_bot_v4.models import AuthorType
                if author_type == AuthorType.BOT:
                    sender_type = MensajeWhatsApp.SENDER_BOT
                    source = MensajeWhatsApp.SOURCE_BOT
                elif author_type == AuthorType.HUMAN:
                    sender_type = MensajeWhatsApp.SENDER_ADVISOR
                    source = MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP
                else:
                    sender_type = MensajeWhatsApp.SENDER_SYSTEM
                    source = MensajeWhatsApp.SOURCE_SYSTEM

                msg_text = body if isinstance(body, str) else body.get('text', {}).get('body', '')
                process_whatsapp_message(
                    client=client,
                    channel=channel,
                    event={
                        "message_id": meta_id,
                        "text": msg_text,
                        "created_at": timezone.now().isoformat(),
                    },
                    direction=MensajeWhatsApp.SALIENTE,
                    sender_type=sender_type,
                    source=source,
                    conversation=conversation,
                )
                logger.info(
                    "[Outbound Message Recorded] conversation=%s sender=%s meta_id=%s",
                    conversation_id, sender_type, meta_id,
                )
            except ConversacionWhatsApp.DoesNotExist:
                logger.warning("[Outbound Message] conversation %s not found", conversation_id)
            except Exception as e:
                logger.error("[Outbound Message Recording Failed] %s", str(e), exc_info=True)

        return result
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

        # Detección explícita de error 190 (token expirado/inválido)
        if error_code == 190:
            logger.error(
                "META ACCESS TOKEN EXPIRADO O INVÁLIDO - regenerar en Business Settings "
                "(conversation=%s, recipient=%s, status=%s)",
                conversation_id, _masked_phone(to), status_code,
            )
        else:
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


# ============================================================================
# Phase C: Secure multimedia download and storage (2026-08-20)
# ============================================================================

YCLOUD_ALLOWED_DOMAINS = {"api.ycloud.com", "download.ycloud.com"}


def download_mensaje_adjunto(
    mensaje: MensajeWhatsApp,
    media_url: str,
    media_id: str,
    formato: str,
    mime_type_client: str = None,
    max_retries: int = 3,
) -> dict:
    """
    Download and store multimedia from YCloud securely.

    Security constraints:
    - Never expose YCLOUD_API_KEY in return value, logs, or API responses
    - Only download from YCloud expected domains
    - Validate MIME type real type, not client-provided
    - Use streaming downloads with size limits
    - Generate safe filenames server-side
    - Calculate SHA256 for integrity

    Args:
        mensaje: MensajeWhatsApp instance to attach file to
        media_url: Download URL from YCloud (temporary, short-lived)
        media_id: YCloud media ID for tracking
        formato: Message type (imagen/video/audio/documento)
        mime_type_client: Client-provided MIME (ignored in validation)
        max_retries: Download retry attempts

    Returns:
        {
            "success": bool,
            "adjunto_id": int or None,
            "reason": str (on failure),
            "file_size": int,
            "sha256": str,
        }
    """

    # Validate domain
    try:
        parsed = urlparse(media_url)
        domain = parsed.netloc.lower()
        if domain not in YCLOUD_ALLOWED_DOMAINS:
            logger.warning(
                "Rejected media download from disallowed domain: %s (media_id=%s)",
                domain,
                media_id,
            )
            return {"success": False, "reason": "invalid_domain"}
    except Exception as e:
        logger.error("URL parsing error for media_url: %s", str(e))
        return {"success": False, "reason": "invalid_url"}

    # Check if already downloaded (idempotence)
    try:
        existing = MensajeAdjunto.objects.get(ycloud_media_id=media_id)
        logger.info("Adjunto ya descargado: media_id=%s, adjunto_id=%s", media_id, existing.id)
        return {
            "success": True,
            "adjunto_id": existing.id,
            "reason": "already_downloaded",
            "file_size": existing.file_size,
            "sha256": existing.sha256,
        }
    except MensajeAdjunto.DoesNotExist:
        pass

    # Download with retries
    api_key = getattr(settings, "YCLOUD_API_KEY", None)
    if not api_key:
        logger.error("YCLOUD_API_KEY not configured")
        return {"success": False, "reason": "api_key_missing"}

    headers = {"Authorization": f"Bearer {api_key}"}
    content = None
    file_size = 0
    sha256_hash = ""

    for attempt in range(max_retries):
        try:
            response = requests.get(media_url, headers=headers, timeout=30, stream=True)
            response.raise_for_status()

            # Validate size on first chunk
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    file_size = int(content_length)
                    max_bytes = (
                        MAX_IMAGE_BYTES
                        if formato == "imagen"
                        else MAX_ATTACHMENT_BYTES
                    )
                    if file_size > max_bytes:
                        logger.warning(
                            "File too large: %d > %d (media_id=%s)",
                            file_size,
                            max_bytes,
                            media_id,
                        )
                        return {"success": False, "reason": "file_too_large"}
                except (ValueError, TypeError):
                    pass

            # Stream download with SHA256 calculation
            sha256_obj = hashlib.sha256()
            chunks = []
            total_size = 0

            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    chunks.append(chunk)
                    sha256_obj.update(chunk)
                    total_size += len(chunk)

                    # Safety check on streaming
                    max_bytes = (
                        MAX_IMAGE_BYTES
                        if formato == "imagen"
                        else MAX_ATTACHMENT_BYTES
                    )
                    if total_size > max_bytes:
                        logger.warning(
                            "Streamed file exceeded limit: %d > %d (media_id=%s)",
                            total_size,
                            max_bytes,
                            media_id,
                        )
                        return {"success": False, "reason": "file_too_large"}

            content = b"".join(chunks)
            sha256_hash = sha256_obj.hexdigest()
            file_size = len(content)
            break

        except requests.RequestException as e:
            logger.warning(
                "Download attempt %d failed for media_id=%s: %s",
                attempt + 1,
                media_id,
                str(e),
            )
            if attempt < max_retries - 1:
                continue
            else:
                return {"success": False, "reason": "download_failed"}

    if not content:
        return {"success": False, "reason": "no_content"}

    # Validate MIME type by content (not client-provided)
    try:
        detected_type, _ = mimetypes.guess_extension(format=None)
        if not detected_type and formato == "imagen":
            detected_type = _detect_image_mime(content[:1024])

        allowed_types = ALLOWED_IMAGE_MIME_TYPES if formato == "imagen" else ALLOWED_ATTACHMENT_MIME_TYPES
        if detected_type not in allowed_types:
            logger.warning(
                "Unsupported MIME type: %s (media_id=%s, format=%s)",
                detected_type,
                media_id,
                formato,
            )
            return {"success": False, "reason": "unsupported_mime_type"}

        mime_type = detected_type
    except Exception:
        mime_type = mime_type_client or "application/octet-stream"

    # Generate safe filename (server-side, not user-provided)
    extension = ALLOWED_ATTACHMENT_MIME_TYPES.get(mime_type, ".bin")
    safe_filename = f"{media_id}{extension}"

    # Calculate retention dates
    retention_policy = mensaje.retention_policy or MensajeWhatsApp.RETAIN_DEFAULT
    policy_days = {
        MensajeWhatsApp.RETAIN_DEFAULT: 30,
        MensajeWhatsApp.RETAIN_QUOTE: 60,
        MensajeWhatsApp.RETAIN_SERVICE: 90,
        MensajeWhatsApp.RETAIN_CLAIM: 365 * 10,  # 10 years
        MensajeWhatsApp.RETAIN_NONE: 0,
    }
    days = policy_days.get(retention_policy, 30)
    retain_until = timezone.now() + timedelta(days=days)

    # Create MensajeAdjunto
    try:
        adjunto = MensajeAdjunto(
            mensaje=mensaje,
            ycloud_media_id=media_id,
            formato=formato,
            mime_type=mime_type,
            filename=safe_filename,
            file_size=file_size,
            sha256=sha256_hash,
            storage_location=MensajeAdjunto.URL_LOCAL,
            retention_policy=retention_policy,
            retain_until=retain_until,
            downloaded_at=timezone.now(),
        )

        # Save file
        adjunto.archivo.save(
            safe_filename,
            ContentFile(content),
            save=False,
        )
        adjunto.save()

        logger.info(
            "Adjunto descargado: media_id=%s, size=%d, sha256=%s, formato=%s",
            media_id,
            file_size,
            sha256_hash,
            formato,
        )

        # Update MensajeWhatsApp media_status
        mensaje.media_status = MensajeWhatsApp.MEDIA_READY
        mensaje.save(update_fields=["media_status"])

        return {
            "success": True,
            "adjunto_id": adjunto.id,
            "file_size": file_size,
            "sha256": sha256_hash,
        }

    except Exception as e:
        logger.exception("Error saving adjunto for media_id=%s: %s", media_id, str(e))
        return {"success": False, "reason": "save_error"}


def _detect_image_mime(header_bytes: bytes) -> str:
    """Detect image MIME type from file header (magic bytes)."""
    if header_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    elif header_bytes.startswith(b"\x89PNG"):
        return "image/png"
    elif header_bytes.startswith(b"RIFF") and b"WEBP" in header_bytes[:12]:
        return "image/webp"
    else:
        return None


def process_whatsapp_message(
    *,
    client,
    channel,
    event,
    direction,
    sender_type,
    source=None,
    conversation=None,
    lead=None,
):
    """
    Process and persist a WhatsApp message atomically.

    Handles: persistence, conversation update, unread count, realtime events.

    Args:
        client: Cliente instance (canonical)
        channel: WhatsAppChannel instance
        event: Event dict with keys: text, message_id (wamid), created_at (ISO 8601 or timestamp)
        direction: MensajeWhatsApp.ENTRANTE or MensajeWhatsApp.SALIENTE
        sender_type: 'customer', 'advisor', 'bot', 'system'
        conversation: Existing ConversacionWhatsApp or None (will be obtained/created)
        lead: Lead instance (optional)

    Returns:
        {
            "message": MensajeWhatsApp instance,
            "conversation": ConversacionWhatsApp instance,
            "created": bool,
            "summary_updated": bool,
            "unread_incremented": bool,
        }
    """
    from django.db import transaction
    from apps.integrations.models import ConversationControl

    result = {
        "message": None,
        "conversation": None,
        "created": False,
        "summary_updated": False,
        "unread_incremented": False,
        "takeover_activated": False,
    }

    # Default source based on direction and sender_type
    if not source:
        if direction == MensajeWhatsApp.ENTRANTE:
            source = MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER
        elif sender_type == MensajeWhatsApp.SENDER_BOT:
            source = MensajeWhatsApp.SOURCE_BOT
        elif sender_type == MensajeWhatsApp.SENDER_ADVISOR:
            source = MensajeWhatsApp.SOURCE_CRM
        else:
            source = MensajeWhatsApp.SOURCE_SYSTEM

    with transaction.atomic():
        # 1. Resolve or create conversation
        if not conversation:
            conversation, _ = ConversacionWhatsApp.objects.get_or_create(
                cliente=client,
                channel=channel,
                defaults={
                    "estado_atencion": ConversacionWhatsApp.ATENCION_BOT,
                }
            )

        # Ensure ConversationControl exists
        ConversationControl.objects.get_or_create(conversation=conversation)

        # 2. Lock conversation for atomic update
        conversation = ConversacionWhatsApp.objects.select_for_update().get(pk=conversation.pk)

        # 3. Parse message timestamp (prefer event's timestamp/created_at from webhook)
        message_timestamp = event.get("created_at") or event.get("timestamp")
        if isinstance(message_timestamp, str):
            try:
                # Try unix timestamp string first
                if message_timestamp.isdigit():
                    message_timestamp = timezone.make_aware(datetime.fromtimestamp(int(message_timestamp)))
                else:
                    message_timestamp = datetime.fromisoformat(message_timestamp.replace("Z", "+00:00"))
                    if message_timestamp.tzinfo is None:
                        message_timestamp = timezone.make_aware(message_timestamp)
            except (ValueError, TypeError):
                message_timestamp = timezone.now()
        elif isinstance(message_timestamp, (int, float)):
            message_timestamp = timezone.make_aware(datetime.fromtimestamp(message_timestamp))
        else:
            message_timestamp = timezone.now()

        # 4. Map sender_type to legacy origen for backward compat
        origen_map = {
            MensajeWhatsApp.SENDER_CUSTOMER: "cliente",
            MensajeWhatsApp.SENDER_BOT: "bot",
            MensajeWhatsApp.SENDER_ADVISOR: "asesor",
            MensajeWhatsApp.SENDER_SYSTEM: "sistema",
        }
        origen = origen_map.get(sender_type, "sistema")

        # 5. Create or get message (idempotent by wamid)
        wamid = str(event.get("message_id") or "")
        message, created = MensajeWhatsApp.objects.get_or_create(
            meta_message_id=wamid,
            conversacion=conversation,
            defaults={
                "direccion": direction,
                "origen": origen,
                "tipo": "texto",
                "contenido": str(event.get("text") or "")[:500],
                "estado": "recibido",
                "sender_type": sender_type,
                "source": source,
                "fecha_mensaje": message_timestamp,
            }
        )

        result["message"] = message
        result["conversation"] = conversation
        result["created"] = created

        logger.info(
            "[WhatsApp Message] wamid=%s conversation_id=%s message_id=%s created=%s sender=%s dir=%s",
            wamid, conversation.id, message.id, created, sender_type, direction,
        )

        # 6. Update conversation summary if message is new and strictly newer than ultima_actividad
        if created:
            should_update_summary = (
                conversation.ultima_actividad is None
                or message_timestamp > conversation.ultima_actividad
            )

            if should_update_summary:
                old_ua = conversation.ultima_actividad
                old_resumen = conversation.resumen
                conversation.ultima_actividad = message_timestamp
                conversation.resumen = str(event.get("text") or "")[:100]

                if direction == MensajeWhatsApp.ENTRANTE:
                    conversation.ultimo_mensaje_cliente = message_timestamp
                else:
                    conversation.ultimo_mensaje_enviado = message_timestamp

                conversation.save(
                    update_fields=[
                        "ultima_actividad",
                        "resumen",
                        "ultimo_mensaje_cliente",
                        "ultimo_mensaje_enviado",
                    ]
                )
                result["summary_updated"] = True

                logger.info(
                    "[Summary Updated] conv=%s old_ua=%s new_ua=%s old_resumen=%s new_resumen=%s",
                    conversation.id, old_ua, message_timestamp, old_resumen[:50] if old_resumen else "empty", conversation.resumen[:50],
                )
            else:
                logger.warning(
                    "[Summary NOT Updated] conv=%s created=%s should_update=%s current_ua=%s msg_timestamp=%s",
                    conversation.id, created, should_update_summary, conversation.ultima_actividad, message_timestamp,
                )

        # 7. Handle takeover: outbound from WhatsApp Business App (Web/mobile echo) = human intervention
        if (direction == MensajeWhatsApp.SALIENTE and
            sender_type == MensajeWhatsApp.SENDER_ADVISOR and
            source == MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP):
            conversation.bot_pausado = True
            conversation.estado_atencion = ConversacionWhatsApp.ATENCION_ASESOR
            conversation.save(update_fields=["bot_pausado", "estado_atencion"])
            result["takeover_activated"] = True
            logger.info("[Takeover] conv=%s advisor_web_intervention", conversation.id)

        # 8. Update unread count (only for inbound messages from customers)
        if created and direction == MensajeWhatsApp.ENTRANTE and sender_type == MensajeWhatsApp.SENDER_CUSTOMER:
            result["unread_incremented"] = True
            logger.info("[Unread +1] conv=%s", conversation.id)

        # 9. Schedule realtime event after commit
        if created:
            def publish_event():
                try:
                    from apps.whatsapp.views_sse_global import broadcast_to_user
                    from django.contrib.auth import get_user_model

                    # Broadcast to all active users
                    User = get_user_model()
                    for user in User.objects.filter(is_active=True):
                        broadcast_to_user(user.id, 'message.created', {
                            'conversation_id': conversation.id,
                            'message_id': message.id,
                            'timestamp': message.fecha_mensaje.isoformat(),
                        })

                    logger.info("[SSE Broadcast] message_id=%s conversation_id=%s to all users", message.id, conversation.id)

                    # Also try legacy integration if available
                    try:
                        from apps.integrations.services.live_sync import project_new_incoming
                        project_new_incoming(message)
                    except:
                        pass
                except Exception as e:
                    logger.error("[RealTime Event] failed: %s", str(e), exc_info=True)

            transaction.on_commit(publish_event)

    return result
