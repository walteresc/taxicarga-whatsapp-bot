import hmac
import hashlib
import json
import logging
import os
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import requests

from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp_bot_v4.models import ConversationOwnership, WebhookEvent
from .conversation_service import ConversationService
from .bot_control_service import can_bot_respond

logger = logging.getLogger(__name__)


def _normalize_phone_number(phone):
    """Normalize phone to E.164 format without +.

    Examples:
      +51 967 619 238 → 51967619238
      51967619238 → 51967619238
      +51967619238 → 51967619238
    """
    if not phone:
        return None
    # Remove all non-digit characters
    normalized = ''.join(filter(str.isdigit, str(phone)))
    return normalized if normalized else None


def _resolve_channel_from_payload(event_type, canonical_payload, payload):
    """Resolve WhatsAppChannel from payload business number.

    For inbound (whatsapp.inbound_message.received):
      - Business number is in 'to' field (customer sends TO business)
      - Lookup from whatsappInboundMessage.to

    For echo (whatsapp.smb.message.echoes):
      - Business number is in 'from' field (business sends FROM here)
      - Lookup from whatsappMessage.from

    Returns WhatsAppChannel or None if not found.
    """
    from apps.whatsapp.models import WhatsAppChannel

    business_number = None

    # Extract business number based on event type
    if event_type == "whatsapp.inbound_message.received":
        # Try canonical first, then raw payload
        business_number = canonical_payload.get("to") or \
                         payload.get("whatsappInboundMessage", {}).get("to")
    elif event_type == "whatsapp.smb.message.echoes":
        # Try canonical first, then raw payload
        business_number = canonical_payload.get("from") or \
                         payload.get("whatsappMessage", {}).get("from")

    if not business_number:
        logger.error(f"[YCloud] Cannot extract business number from event {event_type}")
        return None

    # Normalize to E.164 without +
    normalized = _normalize_phone_number(business_number)
    if not normalized:
        logger.error(f"[YCloud] Failed to normalize business number: {business_number}")
        return None

    logger.info(f"[YCloud] Resolving channel for normalized number: {normalized}")

    # Lookup by numero_visible (normalized) or phone_number_id
    channel = WhatsAppChannel.objects.filter(
        activo=True
    ).filter(
        # Match numero_visible (with or without +)
        models.Q(numero_visible=normalized) |
        models.Q(numero_visible=f"+{normalized}") |
        # Also check phone_number_id for backward compatibility
        models.Q(phone_number_id=normalized) |
        models.Q(phone_number_id=f"+{normalized}")
    ).first()

    if channel:
        logger.info(f"[YCloud] Resolved channel {channel.id} ({channel.nombre}) for number {normalized}")
    else:
        logger.error(f"[YCloud] No active channel found for business number {normalized}")

    return channel


def _normalize_ycloud_payload(event_type, payload):
    """Transform YCloud payload format to canonical format expected by YCloudMessageProcessor.

    YCloud format → Canonical format:
    - whatsappInboundMessage → root level fields (from, id, text, etc.)
    - whatsappMessage (echoes) → root level fields (from, to, id, text, etc.)
    - edit events → original message ID + new text (for updates)
    """
    canonical = dict(payload)

    if event_type == "whatsapp.inbound_message.received":
        msg_data = payload.get("whatsappInboundMessage", {})
        if msg_data:
            # Emoji reaction to a message (👍 long-press on WhatsApp) — has no 'text'
            # field at all (only 'reaction': {message_id, emoji}). It doesn't create a
            # new message; it UPDATES the reacted-to one. Handled separately by the
            # view (handle_reaction_event), short-circuited BEFORE the normal
            # client/conversation/message pipeline below — a reaction has no content
            # type of its own to persist as a MensajeWhatsApp row.
            if msg_data.get("type") == "reaction":
                reaction = msg_data.get("reaction") or {}
                canonical["is_reaction"] = True
                canonical["reaction_target_wamid"] = reaction.get("message_id", "")
                canonical["reaction_emoji"] = reaction.get("emoji", "")
                canonical["wamid"] = msg_data.get("id")
                canonical["from"] = msg_data.get("from")

                return canonical

            # Message revoked/deleted by the SENDER on their own side ("delete for
            # everyone" from the customer's WhatsApp) — has no 'text' field at all,
            # only 'revoke': {originalMessageId}. Falling through to the normal
            # branch below created a blank text message (empty contenido) for each
            # one, same bug class as reactions before those were handled. Discarded:
            # we don't fabricate a "mensaje eliminado" placeholder here, same
            # principle as not faking any action we don't fully support yet.
            if msg_data.get("type") == "revoke":
                original = (msg_data.get("revoke") or {}).get("originalMessageId", "")
                logger.info(f"[YCloud] Message revoked by sender (original={original}), discarding event")
                return None

            # Check if this is an EDIT event
            if msg_data.get("type") == "edit" and msg_data.get("edit"):
                edit_data = msg_data.get("edit", {})
                original_msg_id = edit_data.get("originalMessageId")
                edited_msg = edit_data.get("message", {})

                # Extract original message ID (YCloud wamid format)
                canonical["is_edit"] = True
                canonical["original_wamid"] = original_msg_id
                canonical["from"] = msg_data.get("from")
                canonical["from_name"] = (msg_data.get("customerProfile") or {}).get("name") or msg_data.get("fromName", "")
                canonical["from_user_id"] = msg_data.get("fromUserId", "")
                canonical["reply_to_wamid"] = (msg_data.get("context") or {}).get("id", "")
                canonical["wamid"] = original_msg_id  # Use ORIGINAL wamid for lookup
                canonical["text"] = edited_msg.get("text", {}).get("body", "")
                canonical["type"] = "text"
                canonical["timestamp"] = payload.get("timestamp")
            else:
                # Normal inbound message (NOT edited)
                canonical["is_edit"] = False
                canonical["from"] = msg_data.get("from")
                # Contact name: YCloud sends it under customerProfile.name (real field).
                # fromName kept as legacy fallback in case older payload shapes use it.
                canonical["from_name"] = (msg_data.get("customerProfile") or {}).get("name") or msg_data.get("fromName", "")
                # fromUserId is YCloud's opaque persistent identity — present even when
                # 'from' (the phone) is omitted, e.g. on reply/quote messages.
                canonical["from_user_id"] = msg_data.get("fromUserId", "")
                # If this message quotes/replies to a previous one, YCloud sets 'context.id'
                # to that message's wamid — used as an identity fallback when 'from' is absent.
                canonical["reply_to_wamid"] = (msg_data.get("context") or {}).get("id", "")
                canonical["wamid"] = msg_data.get("id")
                # Real WhatsApp/Meta wamid ('wamid.XXXX') — distinct from the YCloud-internal
                # 'id' above. Required for context.message_id when quoting this message later;
                # the YCloud id above does NOT work for that (confirmed: YCloud silently accepts
                # it but WhatsApp never renders the quote — see meta_message_id field docstring).
                canonical["real_wamid"] = msg_data.get("wamid", "")
                canonical["text"] = msg_data.get("text", {}).get("body", "")
                canonical["image"] = msg_data.get("image")
                canonical["audio"] = msg_data.get("audio")
                canonical["document"] = msg_data.get("document")
                canonical["timestamp"] = payload.get("timestamp")

                # Detect content type based on what's present
                if msg_data.get("image"):
                    canonical["type"] = "image"
                elif msg_data.get("audio"):
                    canonical["type"] = "audio"
                elif msg_data.get("document"):
                    canonical["type"] = "document"
                else:
                    canonical["type"] = "text"

    elif event_type == "whatsapp.smb.message.echoes":
        msg_data = payload.get("whatsappMessage", {})
        if msg_data:
            # Advisor revoked/deleted their own message from the native WhatsApp
            # Business app — same "revoke" shape and same fix as the inbound branch
            # above (no 'text' field, would otherwise create a blank message).
            if msg_data.get("type") == "revoke":
                original = (msg_data.get("revoke") or {}).get("originalMessageId", "")
                logger.info(f"[YCloud] Advisor revoked message via WhatsApp app (original={original}), discarding event")
                return None

            # Echo: 'to' is customer, 'from' is business
            canonical["from"] = msg_data.get("from")
            canonical["to"] = msg_data.get("to")
            # Some contacts never expose a phone number via the API at all (confirmed:
            # same contact, same conversation, missing on BOTH inbound and echo/outbound
            # events) — toUserId is the fallback identity, same idea as from_user_id on
            # the inbound side.
            canonical["to_user_id"] = msg_data.get("toUserId", "")
            profile = msg_data.get("customerProfile") or {}
            canonical["to_name"] = profile.get("name") or profile.get("username", "")
            canonical["wamid"] = msg_data.get("id")
            canonical["real_wamid"] = msg_data.get("wamid", "")
            canonical["text"] = msg_data.get("text", {}).get("body", "")
            canonical["type"] = payload.get("type")
            canonical["timestamp"] = payload.get("timestamp")

    elif event_type == "whatsapp.message.updated":
        # Status update (sent/delivered/read/failed) for a message WE sent. The real
        # data is nested under whatsappMessage — payload.get("id")/.get("status") at
        # the top level (the old code here) read the EVENT's own id, not the
        # message's, and there is no top-level "status" key at all: this branch
        # always produced wamid=<event id> status=None, silently no-op forever.
        msg_data = payload.get("whatsappMessage", {})
        canonical["is_status_update"] = True
        canonical["wamid"] = msg_data.get("id")
        canonical["status"] = msg_data.get("status")
        canonical["type"] = "status"

    return canonical if canonical.get("wamid") or canonical.get("from") or canonical.get("status") else None


def verify_ycloud_signature(request):
    """Validar firma HMAC de YCloud según contrato oficial.

    Formato official:
    - Header: Ycloud-Signature: t=<timestamp>,s=<hex_digest>
    - Signed payload: <timestamp>.<raw_request_body_bytes>
    - Algorithm: HMAC-SHA256(endpoint_signing_secret, signed_payload)

    Contrato: https://docs.ycloud.com/reference/configure-webhooks
    """
    from django.conf import settings
    import os

    body = request.body
    signature_header = request.headers.get('Ycloud-Signature', '')

    if not signature_header:
        logger.error("[YCloud] Missing Ycloud-Signature header")
        return False

    # Parse header: t=<ts>,s=<sig>
    parts = {}
    for part in signature_header.split(','):
        if '=' in part:
            key, value = part.split('=', 1)
            parts[key.strip()] = value.strip()

    timestamp = parts.get('t', '')
    signature = parts.get('s', '')

    if not timestamp or not signature:
        logger.error("[YCloud] Malformed Ycloud-Signature header")
        return False

    body = request.body
    secret = settings.YCLOUD_WEBHOOK_SECRET

    # Diagnostic (SAFE - no payload, no secrets, only hashes and metadata)
    if os.environ.get('DEBUG'):
        body_hash_fp = hashlib.sha256(body).hexdigest()[:12]
        secret_fp = hashlib.sha256(secret.encode()).hexdigest()[:8]
        body_len = len(body)
        content_type = request.headers.get('Content-Type', 'unknown')[:50]
        logger.warning(f"[YCloud] HMAC_CHECK: body_len={body_len}, body_hash={body_hash_fp}, secret_hash={secret_fp}, ts={timestamp}, ct={content_type}")

    # OFFICIAL FORMAT: timestamp + "." + raw_body_bytes
    # Use bytes directly to preserve exact payload
    signed_payload = timestamp.encode('ascii') + b'.' + body
    expected_digest = hmac.new(
        secret.encode('utf-8'),
        signed_payload,
        hashlib.sha256
    ).hexdigest()

    match = hmac.compare_digest(signature, expected_digest)

    if not match and os.environ.get('DEBUG'):
        # SAFE: Only log signature comparison, not payload
        logger.warning(f"[YCloud] HMAC_MISMATCH: expected={expected_digest[:8]}, got={signature[:8]}")

    return match


@csrf_exempt
@require_http_methods(["GET", "POST"])
def ycloud_webhook(request):
    """Webhook de YCloud - adaptador delgado que delega al procesador canónico.

    Soporta:
    - GET: Verificación de webhook (Meta/YCloud webhook configuration)
    - POST: Entrega de eventos (mensajes, estado, etc.)

    Responsabilidades POST:
    1. Validar firma HMAC
    2. Registrar evento para idempotencia (WebhookEvent)
    3. Delegar persistencia a YCloudMessageProcessor.process_ycloud_event()
    4. Retornar HTTP 200 inmediatamente (no bloquear por bot processing)
    5. Disparar bot processing en background (si aplica)
    """
    # VERIFICACIÓN DE WEBHOOK (GET request)
    if request.method == "GET":
        hub_mode = request.GET.get("hub.mode")
        hub_challenge = request.GET.get("hub.challenge")
        hub_verify_token = request.GET.get("hub.verify_token")

        if hub_mode == "subscribe" and hub_verify_token == os.environ.get("YCLOUD_WEBHOOK_SECRET", ""):
            logger.warning(f"[YCloud] Webhook verification successful")
            return HttpResponse(hub_challenge, content_type="text/plain")

        logger.warning(f"[YCloud] Webhook verification failed - invalid token or mode")
        return HttpResponse("Unauthorized", status=401)

    from .event_trace_middleware import EventTrace

    logger.warning(f"[YCloud] WEBHOOK HANDLER EXECUTED - RECEIVED AT {timezone.now()}")

    # Initialize tracing
    payload_dict = {}
    try:
        payload_dict = json.loads(request.body)
    except:
        pass
    event_id = payload_dict.get('id', 'unknown')
    wamid = payload_dict.get('whatsappInboundMessage', {}).get('id') or payload_dict.get('whatsappMessage', {}).get('id') or 'unknown'
    trace = EventTrace(event_id, wamid)
    trace.log(1, "WEBHOOK_RECEIVED", f"event_id={event_id}, wamid={wamid}")

    # 1. VALIDAR FIRMA
    if not verify_ycloud_signature(request):
        trace.log(2, "HMAC_VALIDATION_FAILED", "401 returned")
        logger.error("[YCloud] Invalid YCloud signature - REJECTING")
        return JsonResponse({'error': 'Invalid signature'}, status=401)
    trace.log(2, "HMAC_VALIDATION_PASSED", "Format 2 (timestamp.body)")

    # 2. PARSEAR JSON
    try:
        payload = json.loads(request.body)
        trace.log(3, "JSON_PARSED", f"{len(json.dumps(payload))} bytes")
    except json.JSONDecodeError as e:
        trace.log(3, "JSON_PARSE_ERROR", str(e))
        logger.error("[YCloud] Invalid JSON in YCloud webhook")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # 3. EXTRAER METADATOS
    event_type = payload.get('type') or payload.get('event')
    if not event_type:
        trace.log(4, "EVENT_TYPE_MISSING", "400 returned")
        logger.warning("[YCloud] Missing event type")
        return JsonResponse({'error': 'Missing event type'}, status=400)

    event_id = payload.get('id') or payload.get('event_id')
    if not event_id:
        import uuid
        event_id = str(uuid.uuid4())

    trace.log(4, "EVENT_TYPE_EXTRACTED", f"type={event_type}, id={event_id}")
    logger.warning(f"[YCloud] Event type={event_type}, event_id={event_id}")

    # 4. IDEMPOTENCIA: No procesar dos veces
    existing = WebhookEvent.objects.filter(
        source='ycloud',
        external_message_id=event_id
    ).first()
    if existing:
        trace.log(5, "IDEMPOTENCE_CHECK", f"duplicate detected, skipped (PK={existing.id})")
        logger.info(f"[YCloud] Duplicate event {event_id}, skipping")
        return JsonResponse({'status': 'skipped'})
    trace.log(5, "IDEMPOTENCE_CHECK", "unique event")

    # 5. REGISTRAR EVENTO
    try:
        webhook_evt = WebhookEvent.objects.create(
            source='ycloud',
            external_message_id=event_id,
            event_type=event_type
        )
        trace.log(6, "WEBHOOK_EVENT_CREATED", f"PK={webhook_evt.id}")
        logger.warning(f"[YCloud] WebhookEvent created: ID={webhook_evt.id}")
    except Exception as e:
        trace.log(6, "WEBHOOK_EVENT_ERROR", str(e))
        logger.error(f"[YCloud] Error creating WebhookEvent: {e}", exc_info=True)

    # 6. TRANSFORMAR PAYLOAD A FORMATO CANÓNICO
    # YCloud structure → canonical format for processor
    canonical_payload = _normalize_ycloud_payload(event_type, payload)
    if not canonical_payload:
        trace.log(7, "PAYLOAD_NORMALIZATION_FAILED", "returning 200")
        logger.warning("[YCloud] Failed to normalize payload")
        return JsonResponse({'status': 'ok'})
    trace.log(7, "PAYLOAD_NORMALIZED", f"from={canonical_payload.get('from')}, wamid={canonical_payload.get('wamid')}")

    # 6B. REACCIÓN: actualiza un mensaje existente, no crea uno nuevo — short-circuit
    # antes del pipeline normal de cliente/conversación/mensaje.
    if canonical_payload.get("is_reaction"):
        handle_reaction_event(canonical_payload)
        trace.log(11, "HTTP_200_RETURNED", "reaction processed")
        trace.summary()
        return JsonResponse({'status': 'ok'})

    # 6C. STATUS UPDATE (sent/delivered/read/failed): same short-circuit — updates
    # an existing message's estado, never creates one.
    if canonical_payload.get("is_status_update"):
        handle_status_update_event(canonical_payload)
        trace.log(11, "HTTP_200_RETURNED", "status update processed")
        trace.summary()
        return JsonResponse({'status': 'ok'})

    # 7. DELEGAR PERSISTENCIA AL PROCESADOR CANÓNICO
    try:
        logger.warning(f"[YCloud] Resolving channel for event {event_type}")
        # Resolve channel from payload (business number)
        channel = _resolve_channel_from_payload(event_type, canonical_payload, payload)
        if not channel:
            trace.log(8, "CHANNEL_RESOLUTION_FAILED", "no active channel found")
            logger.error(f"[YCloud] Channel resolution FAILED for event {event_type} - SKIPPING")
            return JsonResponse({'status': 'ok'})  # HTTP 200 but no processing
        trace.log(8, "CHANNEL_RESOLVED", f"ch_id={channel.id}, name={channel.nombre}")
        logger.warning(f"[YCloud] Channel resolved: ID={channel.id} ({channel.nombre})")

        # Importar procesador
        from apps.whatsapp.services_ycloud import process_ycloud_event

        # Procesar evento (persistencia atómica: cliente, conversación, mensaje)
        result = process_ycloud_event(event_type, canonical_payload, channel, event_id=event_id)

        if result.get("message"):
            msg_id = result["message"].id
            conv_id = result["conversation"].id
            trace.log(9, "MESSAGE_PERSISTED", f"msg_pk={msg_id}, conv_pk={conv_id}, wamid={result['message'].meta_message_id}")
        else:
            trace.log(9, "MESSAGE_PERSISTENCE_FAILED", str(result.get("error")))

        logger.info(f"[YCloud] Persistence result: {result}")

        # TRANSACTION.ON_COMMIT: Redis publish handled by signal
        trace.log(10, "REDIS_PUBLISH_QUEUED", "via on_commit signal (async)")

        # 8. PROCESAR BOT EN BACKGROUND (no bloquear HTTP 200)
        if result.get("message") and result.get("conversation"):
            try:
                # Disparar bot processing sin esperar (puede ser async en el futuro)
                process_bot_for_conversation_async(result["conversation"], result["message"])
            except Exception as e:
                logger.error(f"[YCloud] Error dispatching bot: {e}", exc_info=True)
                # NO retornar error — mensaje ya fue persistido

    except Exception as e:
        trace.log(9, "PROCESSING_ERROR", str(e)[:100])
        logger.error(f"[YCloud] Error processing event: {e}", exc_info=True)
        # HTTP 200 igual — idempotencia registrada, no intentar de nuevo

    # RETORNAR HTTP 200 (mensaje ya persistido o en queue)
    trace.log(11, "HTTP_200_RETURNED", "processing queued or complete")
    trace.summary()
    return JsonResponse({'status': 'ok'})


def process_bot_for_conversation_async(conversation, message):
    """Procesar respuesta del bot para una conversación.

    Se ejecuta DESPUÉS de retornar HTTP 200 — no bloquea webhook.
    Verifica: bot pausado, control, can_bot_respond, etc.
    """
    from apps.whatsapp_bot_v4.models import ConversationOwnership
    from apps.whatsapp_bot_v4.services.bot_control_service import can_bot_respond

    logger.info(f"[BotAsync] Processing conversation {conversation.id}, message {message.id}")

    # Solo procesar mensajes de cliente (ENTRANTE)
    if message.direccion != MensajeWhatsApp.ENTRANTE:
        logger.info(f"[BotAsync] Skipping non-inbound message {message.id}")
        return

    # Solo procesar si origen es cliente
    if message.origen != MensajeWhatsApp.ORIGEN_CLIENTE:
        logger.info(f"[BotAsync] Skipping non-customer message {message.id}")
        return

    # --- Tercerización de cargas: identifica y enruta ANTES del check de
    # pausa del bot de clientes a propósito — es clasificación/etiquetado
    # para la bandeja del CRM, no una respuesta del bot, así que debe
    # funcionar aunque el bot esté pausado globalmente. Si esta conversación
    # es (o se acaba de identificar como) transportista, el bot de CLIENTES
    # nunca debe verla, ni ahora ni si se reanudara — solo el bot de
    # transportistas (Fase 3, con su propio check de pausa y su propio flag
    # TRANSPORTISTA_BOT_ENABLED) puede responderle.
    try:
        from apps.tercerizacion.services import identificar_posible_transportista
        if identificar_posible_transportista(conversation, message):
            logger.info(f"[BotAsync] Conversation {conversation.id} es transportista")
            from apps.tercerizacion.bot_service import process_transportista_bot_response
            try:
                process_transportista_bot_response(conversation, message)
            except Exception as e:
                logger.error(f"[BotAsync] Error en bot de transportistas: {e}", exc_info=True)
            return
    except Exception as e:
        logger.error(f"[BotAsync] Error identificando transportista: {e}", exc_info=True)
        # No bloquear el flujo normal de cliente por un error aquí

    # Verificar si puede responder el bot (de CLIENTES)
    if not can_bot_respond(conversation.id):
        logger.info(f"[BotAsync] Bot cannot respond for conversation {conversation.id}")
        return

    try:
        process_bot_response(
            conversation.cliente.telefono.lstrip('+'),
            message.contenido,
            conversation
        )
    except Exception as e:
        logger.error(f"[BotAsync] Error processing bot response: {e}", exc_info=True)


# YCloud's own status strings -> our estado choices. "accepted" (the very first
# status, before "sent") intentionally maps to "enviado" too — same tick as sent.
YCLOUD_STATUS_TO_ESTADO = {
    "accepted": "enviado",
    "sent": "enviado",
    "delivered": "entregado",
    "read": "leido",
    "failed": "error",
    "undelivered": "error",
}
ESTADO_TICK_RANK = {"enviado": 1, "entregado": 2, "leido": 3, "error": 0}


def handle_status_update_event(canonical_payload):
    """Update a sent message's estado (sent/delivered/read/failed — WhatsApp Web's
    tick marks) from a whatsapp.message.updated webhook.

    Correlates by meta_message_id — YCloud's own short id, the SAME id captured at
    send time (send_via_ycloud's "wamid" key is actually this short id, an old
    naming leftover; see MensajeWhatsApp.wamid's docstring for why that's a
    DIFFERENT field from the real Meta wamid). Never regresses an already-more-
    advanced status (e.g. a late "delivered" arriving after "read" was already seen).
    """
    correlation_id = canonical_payload.get("wamid", "")
    ycloud_status = canonical_payload.get("status", "")
    nuevo_estado = YCLOUD_STATUS_TO_ESTADO.get(ycloud_status)

    if not correlation_id or not nuevo_estado:
        logger.info(f"[YCloud] Status update ignored: id={correlation_id!r} status={ycloud_status!r}")
        return

    try:
        message = MensajeWhatsApp.objects.get(meta_message_id=correlation_id)
    except MensajeWhatsApp.DoesNotExist:
        logger.info(f"[YCloud] Status update for unknown message meta_message_id={correlation_id}, ignoring")
        return
    except MensajeWhatsApp.MultipleObjectsReturned:
        logger.error(f"[YCloud] Multiple messages share meta_message_id={correlation_id}, ignoring status update")
        return

    if ESTADO_TICK_RANK.get(nuevo_estado, 0) <= ESTADO_TICK_RANK.get(message.estado, 0):
        return

    update_fields = ["estado"]
    message.estado = nuevo_estado
    if nuevo_estado == "entregado" and not message.entregado_en:
        message.entregado_en = timezone.now()
        update_fields.append("entregado_en")
    elif nuevo_estado == "leido" and not message.leido_en:
        message.leido_en = timezone.now()
        update_fields.append("leido_en")

    message.save(update_fields=update_fields)
    logger.info(f"[YCloud] Status: msg_id={message.id} -> {nuevo_estado} (ycloud_status={ycloud_status})")

    from apps.whatsapp.signals import publish_message_media_ready
    publish_message_media_ready(message)


def handle_reaction_event(canonical_payload):
    """Apply an incoming emoji reaction to the message it targets.

    A reaction never creates a MensajeWhatsApp row — it updates the reaction_emoji
    field on the message being reacted to (found by its real wamid) and republishes
    it over SSE so the bubble updates live. An empty emoji means the reaction was
    removed (WhatsApp sends '' explicitly for that) — cleared the same way.
    """
    target_wamid = canonical_payload.get("reaction_target_wamid", "")
    emoji = canonical_payload.get("reaction_emoji", "")

    if not target_wamid:
        logger.warning("[YCloud] Reaction event missing target wamid, ignoring")
        return

    try:
        message = MensajeWhatsApp.objects.get(wamid=target_wamid)
    except MensajeWhatsApp.DoesNotExist:
        logger.warning(f"[YCloud] Reaction target wamid={target_wamid} not found, ignoring")
        return
    except MensajeWhatsApp.MultipleObjectsReturned:
        logger.error(f"[YCloud] Multiple messages share wamid={target_wamid}, ignoring reaction")
        return

    message.reaction_emoji = emoji
    message.save(update_fields=["reaction_emoji"])
    logger.info(f"[YCloud] Reaction {emoji!r} applied to msg_id={message.id} (wamid={target_wamid})")

    from apps.whatsapp.signals import publish_message_media_ready
    publish_message_media_ready(message)

    # Bump conversation activity so the bandeja reorders and the SSE-connected
    # frontend picks it up live — otherwise the conversation stays stuck at its old
    # position/timestamp even though YCloud's own inbox treats a reaction as activity.
    if message.conversacion_id:
        message.conversacion.ultima_actividad = timezone.now()
        message.conversacion.save(update_fields=["ultima_actividad"])


def handle_inbound_message(data):
    """Cliente envió mensaje a través de YCloud

    data = payload (contiene whatsappInboundMessage)
    """
    # YCloud v2 estructura: payload.whatsappInboundMessage
    msg_data = data.get('whatsappInboundMessage', {})

    phone_number = msg_data.get('from', '').lstrip('+')
    message_text = msg_data.get('text', {}).get('body', '')
    message_id = msg_data.get('id')
    contact_name = msg_data.get('fromName', '')  # YCloud proporciona nombre del contacto

    logger.warning(f"[YCloud] Extracted - phone={phone_number}, text={message_text[:50]}, id={message_id}, name={contact_name}")

    if not phone_number or not message_text:
        logger.warning(f"Incomplete inbound message: phone={phone_number}, text={message_text}")
        return

    # Crear cliente si no existe, con nombre si YCloud lo proporciona
    from apps.clientes.models import Cliente
    cliente, created = Cliente.objects.get_or_create(
        telefono=f"+{phone_number}",
        defaults={'nombre': contact_name} if contact_name else {}
    )

    # Actualizar nombre si estaba vacío y ahora tenemos uno
    if not cliente.nombre and contact_name:
        cliente.nombre = contact_name
        cliente.save()

    # Obtener conversación más reciente o crear una nueva
    conversation = ConversacionWhatsApp.objects.filter(cliente=cliente).order_by('-actualizada_en').first()

    if not conversation:
        conversation = ConversacionWhatsApp.objects.create(cliente=cliente)

    # Guardar mensaje del cliente
    msg = MensajeWhatsApp.objects.create(
        conversacion=conversation,
        meta_message_id=message_id,
        direccion=MensajeWhatsApp.ENTRANTE,
        origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        tipo='texto',
        contenido=message_text,
        estado='recibido',
        fecha_mensaje=timezone.now()
    )

    # Cliente escribió → activar bot si estaba pausado globalmente
    if conversation.bot_pausado:
        conversation.bot_pausado = False
        conversation.save(update_fields=['bot_pausado'])

    # NO resetear ownership: asesor devuelve control explícitamente
    # Si no hay ownership, crear con BOT mode
    from apps.whatsapp_bot_v4.models import ConversationOwnership
    try:
        ownership = ConversationOwnership.objects.get(conversation=conversation)
        # No cambiar ownership aquí - dejar que asesor devuelva control explícitamente
    except ConversationOwnership.DoesNotExist:
        # Primera vez: crear con BOT mode
        ConversationOwnership.objects.create(
            conversation=conversation,
            owner_type=ConversationOwnership.OWNER_BOT,
            control_mode=ConversationOwnership.MODE_AUTOMATIC
        )

    logger.info(f"Inbound message saved: conversation={conversation.id}, message_id={message_id}")

    # EXTRACCIÓN DE DATOS: Siempre extraer, incluso si bot pausado globalmente
    try:
        extract_and_fill_lead_data(conversation, message_text)
    except Exception as e:
        logger.error(f"Error extracting lead data: {e}", exc_info=True)

    # PUNTO 1+2: Validación global y de conversación
    if not can_bot_respond(conversation.id):
        logger.info(f"Bot cannot respond for conversation {conversation.id}")
        return

    # Procesar con bot (llamar ConversationService)
    try:
        process_bot_response(phone_number, message_text, conversation)
    except Exception as e:
        logger.error(f"Error processing bot response: {e}", exc_info=True)


def handle_advisor_message(data):
    """Asesor escribió desde WhatsApp Web (YCloud detectó)"""

    # Estructura: data['whatsappMessage']['to'] es el CLIENTE (not 'from' que es el bot)
    msg_data = data.get('whatsappMessage', {})
    client_phone = msg_data.get('to', '').lstrip('+')  # CLIENTE es 'to', no 'from'
    message_text = msg_data.get('text', {}).get('body', '')
    message_id = msg_data.get('id')

    logger.warning(f"[YCloud] Advisor extracted - client_phone={client_phone}, text={message_text[:50] if message_text else 'EMPTY'}, id={message_id}")

    if not client_phone:
        logger.warning("Incomplete advisor message - no client_phone")
        return

    # Buscar conversación del CLIENTE
    try:
        from apps.clientes.models import Cliente
        cliente = Cliente.objects.get(telefono=f"+{client_phone}")
        conversation = ConversacionWhatsApp.objects.filter(cliente=cliente).order_by('-actualizada_en').first()
        if not conversation:
            logger.warning(f"[YCloud] Conversation not found for {client_phone}")
            return
    except Cliente.DoesNotExist:
        logger.warning(f"[YCloud] Cliente not found for {client_phone}")
        return

    # Guardar mensaje del asesor
    MensajeWhatsApp.objects.create(
        conversacion=conversation,
        meta_message_id=message_id,
        direccion=MensajeWhatsApp.SALIENTE,
        origen=MensajeWhatsApp.ORIGEN_ASESOR,
        tipo='texto',
        contenido=message_text,
        estado='enviado'
    )

    # Pausa bot automática
    ownership, _ = ConversationOwnership.objects.get_or_create(conversation=conversation)
    ownership.owner_type = ConversationOwnership.OWNER_ADVISOR
    ownership.last_human_message_at = timezone.now()
    ownership.save()

    logger.info(f"Advisor message detected via YCloud, bot paused for conversation {conversation.id}")


def handle_message_update(data):
    """Actualización de estado de mensaje (sent, delivered, read)"""
    message_id = data.get('id')
    status = data.get('status')

    try:
        msg = MensajeWhatsApp.objects.get(meta_message_id=message_id)
        msg.estado = status
        msg.save(update_fields=['estado'])
        logger.info(f"Message {message_id} status updated to {status}")
    except MensajeWhatsApp.DoesNotExist:
        logger.warning(f"Message {message_id} not found for status update")


def process_bot_response(phone_number, message_text, conversation):
    """Procesar respuesta del bot con OpenAI

    PUNTO 3: Validación antes de LLM
    PUNTO 4: Validación antes de enviar
    """
    from openai import OpenAI
    from django.conf import settings

    # PUNTO 3: Validar nuevamente antes de LLM
    if not can_bot_respond(conversation.id):
        logger.warning(f"Response blocked pre-LLM: control changed for conversation {conversation.id}")
        return

    logger.info(f"Processing bot response for {phone_number}: {message_text}")

    # Obtener historial de conversación (últimos 15 mensajes para incluir contexto del asesor)
    historial = list(MensajeWhatsApp.objects.filter(conversacion=conversation).order_by('fecha_mensaje').values('origen', 'contenido'))[-15:]

    messages = []
    for msg in historial:
        if msg['origen'] == MensajeWhatsApp.ORIGEN_CLIENTE:
            role = "user"
            content = msg['contenido']
        elif msg['origen'] == MensajeWhatsApp.ORIGEN_ASESOR:
            # Asesor: prefijo para que OpenAI entienda el contexto
            role = "user"
            content = f"[ASESOR]: {msg['contenido']}"
        else:  # BOT
            role = "assistant"
            content = msg['contenido']

        messages.append({"role": role, "content": content})

    # Agregar mensaje actual del cliente
    messages.append({"role": "user", "content": message_text})

    # Llamar a OpenAI
    try:
        logger.info(f"Creating OpenAI client with key: {settings.OPENAI_API_KEY[:20]}...")
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info(f"OpenAI client created. Calling with model: {settings.OPENAI_MODEL}")
        logger.info(f"Messages to send: {messages}")

        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": """Eres asistente para empresa de mudanzas.

INSTRUCCIONES CRÍTICAS:
- LEE EL CONTEXTO COMPLETO incluyendo mensajes de asesor (marcados [ASESOR])
- NUNCA contradijas lo que dijo el asesor. Si asesor sugirió algo, APOYA la sugerencia
- Una pregunta a la vez. 1-2 oraciones máximo
- Sé amable y profesional

FLUJO:
1. Recopila: origen, destino, qué se mueve, embalaje sí/no
2. Da PRECIO (lo principal)
3. Solo si cliente reserva: pide fecha
4. Si solo consulta: no insistas en datos adicionales

Ejemplo: Si asesor dice "pueden enviar fotos", NO digas "no es necesario". Continúa respetando esa sugerencia."""},
                *messages
            ],
            temperature=0.7,
            max_tokens=80
        )
        response_text = response.choices[0].message.content
        logger.info(f"OpenAI response received: {response_text}")
    except Exception as e:
        logger.error(f"Error calling OpenAI: {e}", exc_info=True)
        response_text = "Disculpa, hay un problema técnico. Por favor intenta más tarde."

    # PUNTO 4: Validar nuevamente justo antes de enviar
    if not can_bot_respond(conversation.id):
        logger.warning(f"Response blocked pre-send: control changed to asesor for conversation {conversation.id}")
        return

    send_via_ycloud(phone_number, response_text)

    # Guardar respuesta
    MensajeWhatsApp.objects.create(
        conversacion=conversation,
        direccion=MensajeWhatsApp.SALIENTE,
        origen=MensajeWhatsApp.ORIGEN_BOT,
        tipo='texto',
        contenido=response_text,
        estado='enviado'
    )


def send_via_ycloud(phone_number, message_text, reply_to_wamid=None):
    """Enviar mensaje via YCloud API v2.

    reply_to_wamid: optional wamid of a previous message to quote-reply to —
    sent as context.message_id per docs.ycloud.com/reference/whatsapp_message-send.

    Returns a dict, never raises for HTTP/network failures:
      success -> {"success": True, "wamid": <id>, "raw": <response json>}
      failure -> {"success": False, "code": <str>, "message": <str>,
                  "status_code": <int|None>, "raw": <parsed body or {}>}
    """
    import requests

    # ENDPOINT CORRECTO
    url = "https://api.ycloud.com/v2/whatsapp/messages"

    headers = {
        'X-API-Key': settings.YCLOUD_API_KEY,
        'Content-Type': 'application/json'
    }

    # Normalizar números (asegurar E.164 format: +XXXXXXXXXXX)
    recipient = phone_number if phone_number.startswith('+') else f'+{phone_number}'
    sender = settings.YCLOUD_SENDER_PHONE if settings.YCLOUD_SENDER_PHONE.startswith('+') else f'+{settings.YCLOUD_SENDER_PHONE}'

    # PAYLOAD CORRECTO (text debe ser objeto con body)
    payload = {
        'from': sender,
        'to': recipient,
        'type': 'text',
        'text': {
            'body': message_text
        }
    }

    if reply_to_wamid:
        payload['context'] = {'message_id': reply_to_wamid}

    logger.info(f"[YCloud] Sending to {recipient}: {message_text[:50]}")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
    except requests.RequestException as e:
        logger.error(f"[YCloud] Send request failed: {e}")
        return {"success": False, "code": "network_error", "message": str(e), "status_code": None, "raw": {}}

    logger.warning(f"[YCloud] STATUS: {response.status_code}")
    logger.warning(f"[YCloud] RESPONSE: {response.text}")

    if response.status_code in (200, 202):
        data = response.json()
        logger.info(f"[YCloud] Message accepted: {data.get('id')}")
        return {"success": True, "wamid": data.get("id", ""), "raw": data}

    try:
        error_body = response.json()
    except ValueError:
        error_body = {}

    code = error_body.get("code") or f"http_{response.status_code}"
    message = error_body.get("message") or response.text[:300]
    logger.error(f"[YCloud] Error {response.status_code} ({code}): {message}")

    return {
        "success": False,
        "code": code,
        "message": message,
        "status_code": response.status_code,
        "raw": error_body,
    }


def send_reaction_via_ycloud(phone_number, target_wamid, emoji):
    """Send an emoji reaction to a previous message via YCloud API v2.

    target_wamid: the REAL WhatsApp/Meta wamid ('wamid.XXXX') of the message being
    reacted to — same requirement as context.message_id for replies (YCloud's own
    internal id does not work here).
    emoji: '' removes an existing reaction (per docs.ycloud.com/reference/whatsapp_message-send).

    Returns the same success/failure dict shape as send_via_ycloud.
    """
    import requests

    url = "https://api.ycloud.com/v2/whatsapp/messages"

    headers = {
        'X-API-Key': settings.YCLOUD_API_KEY,
        'Content-Type': 'application/json'
    }

    recipient = phone_number if phone_number.startswith('+') else f'+{phone_number}'
    sender = settings.YCLOUD_SENDER_PHONE if settings.YCLOUD_SENDER_PHONE.startswith('+') else f'+{settings.YCLOUD_SENDER_PHONE}'

    payload = {
        'from': sender,
        'to': recipient,
        'type': 'reaction',
        'reaction': {
            'message_id': target_wamid,
            'emoji': emoji,
        },
    }

    logger.info(f"[YCloud] Sending reaction {emoji!r} to {recipient} (target={target_wamid})")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
    except requests.RequestException as e:
        logger.error(f"[YCloud] Reaction send request failed: {e}")
        return {"success": False, "code": "network_error", "message": str(e), "status_code": None, "raw": {}}

    logger.warning(f"[YCloud] REACTION STATUS: {response.status_code}")
    logger.warning(f"[YCloud] REACTION RESPONSE: {response.text}")

    if response.status_code in (200, 202):
        data = response.json()
        return {"success": True, "wamid": data.get("id", ""), "raw": data}

    try:
        error_body = response.json()
    except ValueError:
        error_body = {}

    code = error_body.get("code") or f"http_{response.status_code}"
    message = error_body.get("message") or response.text[:300]
    logger.error(f"[YCloud] Reaction error {response.status_code} ({code}): {message}")

    return {
        "success": False,
        "code": code,
        "message": message,
        "status_code": response.status_code,
        "raw": error_body,
    }


def upload_media_to_ycloud(sender_phone, file_bytes, filename, content_type):
    """Upload a file to YCloud so it can be referenced by id in a subsequent send.

    Docs: POST /v2/whatsapp/media/{phoneNumber}/upload (multipart, field 'file').
    Returns {"success": True, "media_id": str} or the same error shape as send_via_ycloud.
    """
    import requests

    url = f"https://api.ycloud.com/v2/whatsapp/media/{sender_phone}/upload"
    headers = {'X-API-Key': settings.YCLOUD_API_KEY}
    files = {'file': (filename, file_bytes, content_type)}

    try:
        response = requests.post(url, headers=headers, files=files, timeout=30)
    except requests.RequestException as e:
        logger.error(f"[YCloud] Media upload request failed: {e}")
        return {"success": False, "code": "network_error", "message": str(e), "status_code": None, "raw": {}}

    if response.status_code in (200, 201):
        data = response.json()
        logger.info(f"[YCloud] Media uploaded: {data.get('id')}")
        return {"success": True, "media_id": data.get("id", ""), "raw": data}

    try:
        error_body = response.json()
    except ValueError:
        error_body = {}

    code = error_body.get("code") or f"http_{response.status_code}"
    message = error_body.get("message") or response.text[:300]
    logger.error(f"[YCloud] Media upload error {response.status_code} ({code}): {message}")

    return {
        "success": False,
        "code": code,
        "message": message,
        "status_code": response.status_code,
        "raw": error_body,
    }


def send_media_via_ycloud(sender_phone, recipient_phone, media_type, media_id, caption=None, filename=None):
    """Send an already-uploaded media message via YCloud API v2.

    media_type: 'image' | 'audio' | 'video' | 'document' (English, YCloud's own contract).
    'audio' does not support caption or filename per YCloud docs.
    """
    import requests

    url = "https://api.ycloud.com/v2/whatsapp/messages"
    headers = {
        'X-API-Key': settings.YCLOUD_API_KEY,
        'Content-Type': 'application/json',
    }

    media_object = {"id": media_id}
    if caption and media_type in ("image", "video", "document"):
        media_object["caption"] = caption
    if filename and media_type == "document":
        media_object["filename"] = filename

    payload = {
        "from": sender_phone,
        "to": recipient_phone,
        "type": media_type,
        media_type: media_object,
    }

    logger.info(f"[YCloud] Sending {media_type} (media_id={media_id}) to {recipient_phone}")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
    except requests.RequestException as e:
        logger.error(f"[YCloud] Media send request failed: {e}")
        return {"success": False, "code": "network_error", "message": str(e), "status_code": None, "raw": {}}

    if response.status_code in (200, 202):
        data = response.json()
        logger.info(f"[YCloud] Media message accepted: {data.get('id')}")
        return {"success": True, "wamid": data.get("id", ""), "raw": data}

    try:
        error_body = response.json()
    except ValueError:
        error_body = {}

    code = error_body.get("code") or f"http_{response.status_code}"
    message = error_body.get("message") or response.text[:300]
    logger.error(f"[YCloud] Media send error {response.status_code} ({code}): {message}")

    return {
        "success": False,
        "code": code,
        "message": message,
        "status_code": response.status_code,
        "raw": error_body,
    }


def extract_and_fill_lead_data(conversation, message_text):
    """Extraer datos del mensaje y llenar ficha del Lead.
    Se ejecuta SIEMPRE, incluso con bot pausado globalmente.
    """
    from openai import OpenAI
    from apps.leads.models import Lead
    from django.conf import settings

    if not conversation.lead_id:
        logger.info(f"[DataExtraction] No lead for conversation {conversation.id}")
        return

    lead = conversation.lead

    # Prompt para extracción
    extraction_prompt = """Analiza este mensaje de cliente y extrae los siguientes datos si están presentes:
- Origen (dirección o distrito)
- Destino (dirección o distrito)
- Tipo de servicio (mudanza, carga, etc)
- Piso origen
- Piso destino
- Tiene ascensor origen
- Tiene ascensor destino
- Objetos a mover (sofá, cama, escritorio, etc)
- Requiere embalaje
- Fecha aproximada

Responde SOLO con JSON sin explicación:
{"origen": "...", "destino": "...", "tipo": "...", ...}
Si no encuentras un dato, omítelo del JSON.

Mensaje: {message}"""

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Eres un asistente que extrae datos de mensajes de clientes. Responde SOLO con JSON."},
                {"role": "user", "content": extraction_prompt.format(message=message_text)}
            ],
            temperature=0.3,
            max_tokens=200
        )

        import json
        data = json.loads(response.choices[0].message.content)

        # Llenar campos del Lead
        if data.get('origen'):
            lead.distrito_origen = data['origen'][:100]
        if data.get('destino'):
            lead.distrito_destino = data['destino'][:100]
        if data.get('tipo'):
            lead.tipo_servicio = data['tipo'][:50]
        if data.get('piso_origen'):
            lead.piso_origen = int(data['piso_origen']) if str(data['piso_origen']).isdigit() else None
        if data.get('piso_destino'):
            lead.piso_destino = int(data['piso_destino']) if str(data['piso_destino']).isdigit() else None
        if 'ascensor_origen' in data:
            lead.ascensor_origen = data['ascensor_origen'].lower() in ['si', 'sí', 'true', '1']
        if 'ascensor_destino' in data:
            lead.ascensor_destino = data['ascensor_destino'].lower() in ['si', 'sí', 'true', '1']
        if data.get('objetos'):
            lead.lista_objetos = data['objetos'][:500]
        if 'embalaje' in data:
            lead.modalidad_servicio = "con_embalaje" if data['embalaje'].lower() in ['si', 'sí', 'true', '1'] else "solo_transporte"
        if data.get('fecha'):
            lead.fecha_servicio = data['fecha'][:100]

        lead.save()
        logger.info(f"[DataExtraction] Lead {lead.id} updated with: {list(data.keys())}")

    except Exception as e:
        logger.warning(f"[DataExtraction] Error extracting data: {e}")


def process_pending_conversations():
    """Al activar bot: revisar conversaciones donde cliente escribió sin respuesta"""
    from datetime import timedelta
    from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp

    # Conversaciones activas en últimas 24h
    conversations = ConversacionWhatsApp.objects.filter(
        creada_en__gte=timezone.now() - timedelta(hours=24),
        estado_atencion__in=['bot', 'asesor']
    ).select_related('cliente')

    for conversation in conversations:
        # Último mensaje de cliente
        last_client_msg = MensajeWhatsApp.objects.filter(
            conversacion=conversation,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE
        ).order_by('-fecha_mensaje').first()

        if not last_client_msg:
            continue

        # Hay respuesta del bot después del último mensaje del cliente?
        last_bot_msg = MensajeWhatsApp.objects.filter(
            conversacion=conversation,
            origen=MensajeWhatsApp.ORIGEN_BOT,
            fecha_mensaje__gt=last_client_msg.fecha_mensaje
        ).first()

        # Si no hay respuesta del bot, procesar
        if not last_bot_msg:
            logger.info(f"[PendingConv] Conv {conversation.id}: cliente sin respuesta desde {last_client_msg.fecha_mensaje}")
            try:
                process_bot_response(
                    conversation.cliente.telefono.lstrip('+'),
                    last_client_msg.contenido,
                    conversation
                )
            except Exception as e:
                logger.error(f"[PendingConv] Error processing {conversation.id}: {e}", exc_info=True)
