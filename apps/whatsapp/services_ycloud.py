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
                # Fallback: Extract phone based on event type (for backward compatibility)
                if event_type == self.EVENT_ECHO:
                    # Echo: 'to' is the customer, 'from' is the business
                    phone = event_data.get("to")
                    if not phone:
                        result["error"] = "Echo event missing 'to' field (customer phone)"
                        _mark_event_discarded(event_id, "Echo missing 'to' (customer phone)", event_data)
                        return result
                else:
                    # Inbound: 'from' is the customer
                    phone = event_data.get("from") or event_data.get("phone")
                    if not phone:
                        result["error"] = "No phone number in event"
                        _mark_event_discarded(event_id, "Inbound missing 'from' and 'phone'", event_data)
                        return result

                # Normalize phone BEFORE lookup to ensure consistent get_or_create matching
                # Apply the same normalization that Cliente.save() does
                from apps.clientes.phone_normalizer import normalize_phone
                norm_result = normalize_phone(phone)
                if norm_result["is_valid"]:
                    phone_for_lookup = norm_result["normalized_e164"]
                else:
                    # Fallback: minimal normalization (just add + if missing)
                    phone_for_lookup = f'+{phone}' if phone and not phone.startswith('+') else phone

                # Use from_name if provided (YCloud contact name), else phone
                default_name = event_data.get("from_name") or phone
                cliente, created = Cliente.objects.get_or_create(
                    telefono=phone_for_lookup,
                    defaults={"nombre": default_name}
                )
                # Update name if it was default phone and now we have from_name
                if created and event_data.get("from_name") and cliente.nombre == phone:
                    cliente.nombre = event_data.get("from_name")
            else:
                # Cliente already resolved by views.py — just update last interaction
                created = False

            # Update last interaction timestamp (always)
            cliente.ultima_interaccion = timezone.now()
            update_fields = ["ultima_interaccion"]
            if event_data.get("from_name") and (not hasattr(cliente, '_from_name_checked') or not cliente._from_name_checked):
                if cliente.nombre != event_data.get("from_name"):
                    cliente.nombre = event_data.get("from_name")
                    update_fields.append("nombre")
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
                if wamid:
                    message, created = MensajeWhatsApp.objects.get_or_create(
                        meta_message_id=wamid,
                        conversacion=conversation,
                        defaults={
                            "direccion": classification["direction"],
                            "origen": self._map_to_origen(classification["sender_type"]),
                            "tipo": message_type,
                            "contenido": message_text[:500],
                            "estado": "recibido",
                            "sender_type": classification["sender_type"],
                            "source": classification["source"],
                            "fecha_mensaje": message_timestamp,
                        }
                    )
                else:
                    created = True
                    message = MensajeWhatsApp.objects.create(
                        conversacion=conversation,
                        direccion=classification["direction"],
                        origen=self._map_to_origen(classification["sender_type"]),
                        tipo=message_type,
                        contenido=message_text[:500],
                        estado="recibido",
                        sender_type=classification["sender_type"],
                        source=classification["source"],
                        fecha_mensaje=message_timestamp,
                    )

            result["created"] = created
            result["message"] = message
            result["conversation"] = conversation

            # 7. Update conversation only if message is NEW
            if created:
                should_update = (
                    not conversation.ultima_actividad or
                    message_timestamp > conversation.ultima_actividad
                )

                if should_update:
                    old_ua = conversation.ultima_actividad
                    conversation.ultima_actividad = message_timestamp
                    conversation.resumen = message_text[:100] if message_type == "texto" else f"[{message_type}]"

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
                        "[YCloud] Conv %s updated: ua %s → %s, resumen=%s",
                        conversation.id, old_ua, message_timestamp, conversation.resumen[:50]
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
