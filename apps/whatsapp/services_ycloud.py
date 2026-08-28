"""
YCloud central message processing service.

Single entry point for all WhatsApp events.
Handles classification, persistence, and conversation updates atomically.
"""
import logging
from datetime import datetime
from django.db import transaction
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.whatsapp_bot_v4.models import WebhookEvent

logger = logging.getLogger(__name__)


def _mark_event_discarded(event_id, reason, payload_full):
    """Register discarded event with full raw payload."""
    if not event_id:
        return
    try:
        WebhookEvent.objects.filter(
            source='ycloud',
            external_message_id=event_id
        ).update(
            discard_reason=reason,
            discard_payload=payload_full,
            discarded_at=timezone.now()
        )
    except Exception as e:
        logger.error(f"[YCloud] Error marking event {event_id} discarded: {e}", exc_info=True)


class YCloudMessageProcessor:
    """Process WhatsApp events from YCloud webhook with canonical message contract."""

    # Event types
    EVENT_INBOUND = "whatsapp.inbound_message.received"
    EVENT_ECHO = "whatsapp.smb.message.echoes"
    EVENT_STATUS = "whatsapp.message.updated"

    # Classification rules
    def classify_event(self, event_type, event_data):
        """
        Classify YCloud event into canonical direction + sender_type + source.

        Args:
            event_type: str — YCloud event name
            event_data: dict — YCloud event payload

        Returns:
            dict with keys:
                - direction: "inbound" | "outbound"
                - sender_type: "customer" | "bot" | "advisor" | "system"
                - source: "whatsapp_customer" | "whatsapp_business_app" | "crm" | "bot" | "system"
                - human_intervention: bool (True if advisor intervened via WhatsApp Web/mobile)
        """
        classification = {
            "direction": None,
            "sender_type": None,
            "source": None,
            "human_intervention": False,
        }

        if event_type == self.EVENT_INBOUND:
            # Customer sending message via WhatsApp
            classification.update({
                "direction": MensajeWhatsApp.ENTRANTE,
                "sender_type": MensajeWhatsApp.SENDER_CUSTOMER,
                "source": MensajeWhatsApp.SOURCE_WHATSAPP_CUSTOMER,
            })

        elif event_type == self.EVENT_ECHO:
            # WhatsApp Web/mobile echo (advisor sent message from WhatsApp Business app)
            # Check if this wamid was created by CRM before
            wamid = event_data.get("wamid", "")
            if wamid:
                existing = MensajeWhatsApp.objects.filter(meta_message_id=wamid).first()
                if existing and existing.source == MensajeWhatsApp.SOURCE_CRM:
                    # We sent this, ignore echo
                    return None

            # Advisor sent from WhatsApp Web/mobile
            classification.update({
                "direction": MensajeWhatsApp.SALIENTE,
                "sender_type": MensajeWhatsApp.SENDER_ADVISOR,
                "source": MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP,
                "human_intervention": True,
            })

        elif event_type == self.EVENT_STATUS:
            # Status update only — no new message
            return {"status_update_only": True}

        return classification if classification["direction"] else None

    def extract_timestamp(self, event_data):
        """Parse YCloud timestamp into aware datetime."""
        ts = event_data.get("timestamp") or event_data.get("created_at")
        if not ts:
            return timezone.now()

        try:
            if isinstance(ts, str):
                # Unix timestamp string
                if ts.isdigit():
                    return timezone.make_aware(datetime.fromtimestamp(int(ts)))
                # ISO 8601
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            elif isinstance(ts, (int, float)):
                return timezone.make_aware(datetime.fromtimestamp(ts))
        except (ValueError, TypeError):
            pass

        return timezone.now()

    def _get_or_create_cliente_by_phone(self, phone, event_data):
        """Resolve (or create) Cliente from a phone number, normalizing it first."""
        from apps.clientes.phone_normalizer import normalize_phone

        norm_result = normalize_phone(phone)
        if norm_result["is_valid"]:
            phone_for_lookup = norm_result["normalized_e164"]
        else:
            # Fallback: minimal normalization (just add + if missing)
            phone_for_lookup = f'+{phone}' if phone and not phone.startswith('+') else phone

        default_name = event_data.get("from_name") or phone
        cliente, _created = Cliente.objects.get_or_create(
            telefono=phone_for_lookup,
            defaults={"nombre": default_name}
        )
        return cliente

    def _resolve_cliente_by_reply_context(self, event_data):
        """Identity fallback #1: when 'from' is absent, resolve via the quoted message.

        A reply/quote always cites a wamid we've already stored — the safest fallback
        since it doesn't depend on caching an opaque id ahead of time.
        """
        reply_to_wamid = event_data.get("reply_to_wamid")
        if not reply_to_wamid:
            return None
        original = MensajeWhatsApp.objects.filter(
            meta_message_id=reply_to_wamid
        ).select_related("conversacion__cliente").first()
        if original and original.conversacion and original.conversacion.cliente_id:
            logger.info(
                "[YCloud] Resolved cliente via reply context: reply_to=%s -> cliente=%s",
                reply_to_wamid, original.conversacion.cliente_id
            )
            return original.conversacion.cliente
        return None

    def _resolve_cliente_by_from_user_id(self, event_data):
        """Identity fallback #2: match YCloud's opaque fromUserId against a previously
        seen Cliente (cached whenever a message WITH 'from' arrived for that user)."""
        from_user_id = event_data.get("from_user_id")
        if not from_user_id:
            return None
        cliente = Cliente.objects.filter(ycloud_user_id=from_user_id).first()
        if cliente:
            logger.info(
                "[YCloud] Resolved cliente via from_user_id cache: %s -> cliente=%s",
                from_user_id, cliente.id
            )
        return cliente

    @transaction.atomic()
    def process_ycloud_event(self, event_type, event_data, channel, event_id=None, cliente=None):
        """
        Process single YCloud event atomically.

        For echoes: resolves customer from 'to' field, not 'from'.
        For inbound: resolves customer from 'from' field.

        Args:
            event_type: str — EVENT_INBOUND | EVENT_ECHO | EVENT_STATUS
            event_data: dict — Full event payload from YCloud
            channel: WhatsAppChannel instance
            event_id: str — external_message_id for WebhookEvent discard tracking
            cliente: Cliente instance (optional). If provided, use it instead of resolving.

        Returns:
            {
                "created": bool,
                "message": MensajeWhatsApp | None,
                "conversation": ConversacionWhatsApp,
                "human_intervention": bool,
                "error": str | None,
            }
        """
        result = {
            "created": False,
            "message": None,
            "conversation": None,
            "human_intervention": False,
            "error": None,
        }

        try:
            # 1. Classify event
            classification = self.classify_event(event_type, event_data)
            if not classification:
                result["error"] = f"Unknown event type: {event_type}"
                _mark_event_discarded(event_id, f"Unsupported event type: {event_type}", event_data)
                return result

            # Handle status-only updates
            if classification.get("status_update_only"):
                result["error"] = "Status update only — handled separately"
                _mark_event_discarded(event_id, "Status update (no message)", event_data)
                return result

            # 2. Resolve client identity (use provided cliente OR extract from event)
            # If cliente provided by views.py, use it; otherwise resolve from event and mark discards
            if not cliente:
                if event_type == self.EVENT_ECHO:
                    # Echo: 'to' is the customer, 'from' is the business.
                    # 'to' is always present on echoes (the business always knows who it
                    # sent the message to), so no fallback chain is needed here.
                    phone = event_data.get("to")
                    if not phone:
                        result["error"] = "Echo event missing 'to' field (customer phone)"
                        _mark_event_discarded(event_id, "Echo missing 'to' (customer phone)", event_data)
                        return result
                    cliente = self._get_or_create_cliente_by_phone(phone, event_data)
                else:
                    # Inbound: 'from' is the customer. Some inbound messages (replies/quotes
                    # to a previous message) omit 'from' entirely — fall back to resolving
                    # identity via the quoted message, then via a cached opaque user id.
                    phone = event_data.get("from") or event_data.get("phone")
                    if phone:
                        cliente = self._get_or_create_cliente_by_phone(phone, event_data)
                    else:
                        cliente = (
                            self._resolve_cliente_by_reply_context(event_data)
                            or self._resolve_cliente_by_from_user_id(event_data)
                        )
                        if not cliente:
                            result["error"] = "No phone number and no fallback identity resolved"
                            _mark_event_discarded(
                                event_id,
                                "Inbound missing 'from'; reply-context and from_user_id fallback failed",
                                event_data,
                            )
                            return result

            # Update last interaction timestamp, name and identity cache (always, regardless
            # of which resolution path found this cliente)
            cliente.ultima_interaccion = timezone.now()
            update_fields = ["ultima_interaccion"]

            from_name = (event_data.get("from_name") or "").strip()
            if from_name:
                if cliente.channel_profile_name != from_name:
                    cliente.channel_profile_name = from_name
                    update_fields.append("channel_profile_name")
                # Keep nombre/display_name in sync with the WhatsApp profile name as it
                # changes over time (e.g. "firme" -> "Rodrigo") — but never overwrite a
                # name a human has set manually in the CRM (name_source == MANUAL).
                if cliente.name_source != Cliente.SOURCE_MANUAL and cliente.nombre != from_name:
                    cliente.nombre = from_name
                    update_fields.append("nombre")
                    if cliente.display_name != from_name:
                        cliente.display_name = from_name
                        update_fields.append("display_name")
                    if cliente.name_source != Cliente.SOURCE_CHANNEL:
                        cliente.name_source = Cliente.SOURCE_CHANNEL
                        update_fields.append("name_source")

            from_user_id = event_data.get("from_user_id")
            if from_user_id and cliente.ycloud_user_id != from_user_id:
                cliente.ycloud_user_id = from_user_id
                update_fields.append("ycloud_user_id")

            cliente.save(update_fields=update_fields)

            # 3. Resolve or create conversation (using central service)
            from apps.whatsapp.services_conversation_resolver import resolve_or_create_active_conversation
            conversation, conv_created = resolve_or_create_active_conversation(
                cliente=cliente,
                channel=channel,
            )

            # 4. Lock conversation for atomic update
            conversation = ConversacionWhatsApp.objects.select_for_update().get(pk=conversation.pk)

            # 5. Parse message details
            wamid = str(event_data.get("wamid") or event_data.get("message_id") or "")
            message_text = event_data.get("text") or event_data.get("body") or ""
            message_type = self._get_message_type(event_data)
            message_timestamp = self.extract_timestamp(event_data)
            is_edit = event_data.get("is_edit", False)

            # 6. Handle message edits vs. new messages
            if is_edit:
                # This is an edited message — update existing message
                if wamid:
                    try:
                        message = MensajeWhatsApp.objects.get(meta_message_id=wamid, conversacion=conversation)
                        message.contenido = message_text[:500]
                        message.save(update_fields=["contenido"])
                        created = False
                        logger.info(f"[YCloud] Message {wamid} edited: {message_text[:50]}")
                    except MensajeWhatsApp.DoesNotExist:
                        logger.warning(f"[YCloud] Edit event but original message {wamid} not found, creating new")
                        created = True
                        message = MensajeWhatsApp.objects.create(
                            conversacion=conversation,
                            meta_message_id=wamid,
                            direccion=classification["direction"],
                            origen=self._map_to_origen(classification["sender_type"]),
                            tipo=message_type,
                            contenido=message_text[:500],
                            estado="recibido",
                            sender_type=classification["sender_type"],
                            source=classification["source"],
                            fecha_mensaje=message_timestamp,
                        )
                else:
                    logger.error("[YCloud] Edit event but no wamid found")
                    result["error"] = "Edit event missing wamid"
                    return result
            else:
                # Normal new message — get or create
                # Build message defaults (include media fields for multimedia messages)
                msg_defaults = {
                    "direccion": classification["direction"],
                    "origen": self._map_to_origen(classification["sender_type"]),
                    "tipo": message_type,
                    "contenido": message_text[:500],
                    "estado": "recibido",
                    "sender_type": classification["sender_type"],
                    "source": classification["source"],
                    "fecha_mensaje": message_timestamp,
                }

                # Populate media fields if multimedia message
                # NOTE: _normalize_ycloud_payload() nests the media object under the
                # English YCloud type key (event_data["image"|"audio"|"document"]),
                # not under a flat "media_id" key.
                if message_type in ("imagen", "audio", "video", "documento"):
                    media = event_data.get(event_data.get("type", ""), {}) or {}
                    msg_defaults["ycloud_media_id"] = media.get("id", "")
                    msg_defaults["mime_type"] = media.get("mime_type", "")
                    msg_defaults["filename"] = media.get("filename") or media.get("id", "")
                    msg_defaults["file_size"] = 0
                    msg_defaults["sha256"] = media.get("sha256", "")

                if wamid:
                    message, created = MensajeWhatsApp.objects.get_or_create(
                        meta_message_id=wamid,
                        conversacion=conversation,
                        defaults=msg_defaults
                    )
                else:
                    created = True
                    message = MensajeWhatsApp.objects.create(
                        conversacion=conversation,
                        **msg_defaults
                    )

            result["created"] = created
            result["message"] = message
            result["conversation"] = conversation

            # 6.5. Download and persist multimedia attachment (if any).
            # YCloud does not expose an authenticated "GET media by id" endpoint for
            # inbound media — the only access is the short-lived signed 'link' URL
            # embedded in THIS webhook payload. It must be downloaded now; if we defer
            # it, the media becomes permanently unrecoverable once the link expires.
            if message_type in ("imagen", "audio", "video", "documento"):
                media = event_data.get(event_data.get("type", ""), {}) or {}
                media_id = media.get("id", "")
                media_url = media.get("link", "")
                mime_type = media.get("mime_type", "")

                if media_id and media_url and not message.adjuntos.exists():
                    from apps.whatsapp.services import download_mensaje_adjunto

                    def _download_after_commit(
                        msg=message, url=media_url, mid=media_id,
                        fmt=message_type, mime=mime_type,
                    ):
                        dl_result = download_mensaje_adjunto(
                            mensaje=msg,
                            media_url=url,
                            media_id=mid,
                            formato=fmt,
                            mime_type_client=mime,
                        )
                        if not dl_result["success"]:
                            logger.error(
                                "[YCloud] Media download failed: media_id=%s reason=%s",
                                mid, dl_result.get("reason")
                            )

                    transaction.on_commit(_download_after_commit)
                elif media_id and not media_url:
                    logger.warning(
                        "[YCloud] Media message without a download link: media_id=%s type=%s",
                        media_id, message_type
                    )

            # 7. Update conversation based on message timing (not just on creation)
            # FIX: Desacoplar de 'created' — actualizar siempre si el mensaje es más reciente
            # Esto cubre ambas rutas: inbound messages nuevos y echoes de salientes existentes
            should_update_conversation = (
                not conversation.ultima_actividad or
                message_timestamp >= conversation.ultima_actividad  # >= para incluir timestamps iguales
            )

            if should_update_conversation:
                old_ua = conversation.ultima_actividad
                conversation.ultima_actividad = message_timestamp

                # Proteger contra message_text vacío/None
                if message_text and message_text.strip():
                    preview_text = message_text[:100]
                elif message_type == "texto":
                    preview_text = "[Mensaje vacío]"
                else:
                    preview_text = f"[{message_type}]"

                conversation.resumen = preview_text

                if classification["direction"] == MensajeWhatsApp.ENTRANTE:
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
                logger.info(
                    "[YCloud] Conv %s updated: ua %s → %s, resumen=%s, created=%s",
                    conversation.id, old_ua, message_timestamp, conversation.resumen[:50], created
                )

            # 8. Handle human takeover
            if classification.get("human_intervention"):
                conversation.bot_pausado = True
                conversation.estado_atencion = ConversacionWhatsApp.ATENCION_ASESOR
                conversation.save(update_fields=["bot_pausado", "estado_atencion"])
                result["human_intervention"] = True
                logger.info("[YCloud] Human takeover detected: conv %s", conversation.id)

            logger.info(
                "[YCloud Event] type=%s wamid=%s conv=%s created=%s sender=%s dir=%s",
                event_type, wamid, conversation.id, created,
                classification["sender_type"], classification["direction"]
            )

            return result

        except Exception as e:
            logger.exception("[YCloud] Error processing event: %s", e)
            result["error"] = str(e)
            return result

    def _get_message_type(self, event_data):
        """Determine message type from YCloud event."""
        event_type = event_data.get("type", "text")
        type_map = {
            "text": "texto",
            "image": "imagen",
            "audio": "audio",
            "document": "documento",
            "location": "ubicacion",
            "sticker": "sticker",
        }
        return type_map.get(event_type, "texto")

    def _map_to_origen(self, sender_type):
        """Map sender_type to legacy origen field."""
        mapping = {
            MensajeWhatsApp.SENDER_CUSTOMER: MensajeWhatsApp.ORIGEN_CLIENTE,
            MensajeWhatsApp.SENDER_BOT: MensajeWhatsApp.ORIGEN_BOT,
            MensajeWhatsApp.SENDER_ADVISOR: MensajeWhatsApp.ORIGEN_ASESOR,
            MensajeWhatsApp.SENDER_SYSTEM: MensajeWhatsApp.ORIGEN_SISTEMA,
        }
        return mapping.get(sender_type, MensajeWhatsApp.ORIGEN_SISTEMA)


# Singleton instance
_processor = YCloudMessageProcessor()


def process_ycloud_event(event_type, event_data, channel, event_id=None, cliente=None):
    """Public API for processing YCloud events."""
    return _processor.process_ycloud_event(event_type, event_data, channel, event_id=event_id, cliente=cliente)
