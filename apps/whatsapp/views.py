import json
import logging
import hashlib
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.clientes.models import Cliente, Conversacion
from apps.ia.conversation_engine import (
    handle_image_inventory,
    handle_incoming_message,
    next_missing_question_for,
    next_question_targets_for,
)
from apps.ia.image_analyzer import analyze_moving_image
from apps.leads.models import Lead
from apps.integrations.enums import AuthorType, OwnerState
from apps.integrations.models import ConversationControl
from apps.integrations.services.live_sync import canonical_incoming_message
from apps.integrations.services.bot_context import build_bot_context
from apps.integrations.services.bot_runtime import authorize_inbound_trigger
from apps.integrations.services.generations import fail_generation, finalize_generation
from apps.integrations.services.channel_policy import ai_v31_mode, is_feature_enabled
from apps.integrations.services.bot_generation_worker import queue_bot_generation
from apps.integrations.services.meta_sender import process_meta_outbox_event
from apps.whatsapp.domain import obtener_o_crear_conversacion
from apps.whatsapp.identity import resolve_whatsapp_identity

from . import models as whatsapp_models
from .models import BotSchedule, ConfiguracionBot, MensajeWhatsappProcesado, WhatsAppChannel
from .services import download_whatsapp_image, download_whatsapp_media, send_whatsapp_message
from .status import apply_status, extract_statuses
from .utils import extract_event, should_bot_reply, should_bot_handle_lead, evaluar_mixto_inteligente, evaluar_conversacion_avanzada, _marcar_derivacion

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    if request.method == "GET":
        return _verify_webhook(request)
    return _receive_message(request)


def _verify_webhook(request):
    mode = request.GET.get("hub.mode")
    token = request.GET.get("hub.verify_token")
    challenge = request.GET.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        return HttpResponse(challenge or "")
    return HttpResponse("Token invalido", status=403)


def _receive_message(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        logger.warning("Payload WhatsApp invalido.")
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    statuses = extract_statuses(payload)
    if statuses:
        updated = sum(1 for status in statuses if apply_status(status))
        return JsonResponse({"ok": True, "statuses": len(statuses), "updated": updated})

    event = extract_event(payload)
    if not event or not event["phone"]:
        logger.info("Webhook sin mensaje procesable.")
        return JsonResponse({"ok": True, "ignored": True})

    processed = _reserve_message(event)
    if processed is False:
        return JsonResponse({"ok": True, "duplicate": True})

    phone = event["phone"]

    phone_number_id = event.get("phone_number_id", "")
    channel = WhatsAppChannel.objects.filter(phone_number_id=phone_number_id).first()
    if channel is None:
        scope_hash = hashlib.sha256(str(phone_number_id).encode("utf-8")).hexdigest()[:12]
        logger.warning("WhatsApp inbound ignored (reason=unknown_channel, scope_hash=%s).", scope_hash)
        _complete_message(processed)
        return JsonResponse({"ok": True, "ignored": True, "reason": "unknown_channel"})
    if not channel.activo:
        logger.info("WhatsApp inbound ignored (reason=inactive_channel, channel_id=%s).", channel.id)
        _complete_message(processed)
        return JsonResponse({"ok": True, "ignored": True, "reason": "inactive_channel"})

    cliente, resolved_lead, resolved_conversation = resolve_whatsapp_identity(phone, channel)
    cliente.ultima_interaccion = timezone.now()
    cliente.save(update_fields=["ultima_interaccion"])

    try:
        active_lead = resolved_lead or _active_lead(cliente)
        if channel and active_lead and not active_lead.whatsapp_channel_id:
            active_lead.whatsapp_channel = channel
            active_lead.save(update_fields=["whatsapp_channel"])
        if not active_lead and channel and not resolved_conversation:
            active_lead = Lead.objects.create(cliente=cliente, estado=Lead.NUEVO, whatsapp_channel=channel)
        if event["type"] == "image":
            active_lead = _lead_for_image(cliente, active_lead)
            if not active_lead:
                active_lead = Lead.objects.create(cliente=cliente, estado=Lead.NUEVO)
            response = _receive_image(cliente, active_lead, event)
            _complete_message(processed)
            return response
        if event["type"] in {"audio", "document"}:
            active_lead = active_lead or Lead.objects.create(
                cliente=cliente, estado=Lead.NUEVO, whatsapp_channel=channel
            )
            result = download_whatsapp_media(cliente, active_lead, event)
            label = "[Audio recibido]" if event["type"] == "audio" else "[Documento recibido]"
            if event.get("caption"):
                label += f" {event['caption']}"
            Conversacion.objects.create(
                cliente=cliente, mensaje_entrada=label, mensaje_salida="",
                canal=Conversacion.CANAL_WHATSAPP,
            )
            _complete_message(processed)
            return JsonResponse({"ok": True, "media_saved": result.get("saved", False)})
        if event["type"] == "location":
            active_lead = active_lead or Lead.objects.create(
                cliente=cliente, estado=Lead.NUEVO, whatsapp_channel=channel
            )
            Conversacion.objects.create(
                cliente=cliente,
                mensaje_entrada=f"[Ubicación recibida] {event['text']}",
                mensaje_salida="",
                canal=Conversacion.CANAL_WHATSAPP,
            )
            _complete_message(processed)
            return JsonResponse({"ok": True, "location_saved": True})

        bot_deberia_responder = should_bot_reply(lead=active_lead, channel=channel)
        if event["type"] != "text" or not event["text"]:
            logger.info("Tipo de mensaje WhatsApp no procesable: %s", event["type"])
            _complete_message(processed)
            return JsonResponse({"ok": True, "ignored": True})

        message = event["text"]
        canonical_message, _canonical_created, canonical_conversation = canonical_incoming_message(
            lead=active_lead, channel=channel, event=event, conversation=resolved_conversation
        )
        attention_conversation = canonical_conversation or resolved_conversation
        control = (
            ConversationControl.objects.filter(conversation=attention_conversation).first()
            if attention_conversation else None
        )
        human_owned = bool(
            (control and control.owner_state == OwnerState.AGENT_ACTIVE)
            or (attention_conversation and (
                attention_conversation.estado_atencion == attention_conversation.ATENCION_ASESOR
                or attention_conversation.bot_pausado
            ))
        )
        if (
            canonical_message
            and not human_owned
            and (
                is_feature_enabled(canonical_conversation.channel, "return_to_bot")
                or ai_v31_mode(canonical_conversation.channel) == "active"
            )
        ):
            authorization = authorize_inbound_trigger(canonical_message.id)
            if not authorization.authorized:
                Conversacion.objects.create(
                    cliente=cliente, mensaje_entrada=message, mensaje_salida="",
                    canal=Conversacion.CANAL_WHATSAPP,
                )
                _complete_message(processed)
                human_takeover = authorization.integration_message is None
                return JsonResponse({
                    "ok": True,
                    "human_takeover": human_takeover,
                    "duplicate": not human_takeover,
                    "sent": None,
                })
            try:
                if ai_v31_mode(canonical_conversation.channel) == "active":
                    queue_bot_generation(
                        message_id=canonical_message.id,
                        generation_id=authorization.generation.id,
                    )
                    _complete_message(processed)
                    return JsonResponse({
                        "ok":True,"stage8":True,"queued":True,
                        "published":False,"sent":False,
                    })
                context = build_bot_context(
                    canonical_conversation.id, trigger_message_id=canonical_message.id
                )
                reply = handle_incoming_message(
                    cliente, message, canonical_context=context,
                    generation_id=authorization.generation.id,
                )
                question_targets = []
                if active_lead:
                    active_lead.refresh_from_db()
                    question_targets = next_question_targets_for(active_lead)
                _generation, outbox, published = finalize_generation(
                    authorization.generation.id, result_text=reply,
                    question_targets=question_targets,
                )
            except Exception as exc:
                fail_generation(authorization.generation.id, exc)
                raise
            send_result = None
            if published and outbox:
                send_result = process_meta_outbox_event(outbox.id)
            if published:
                Conversacion.objects.create(
                    cliente=cliente, mensaje_entrada=message, mensaje_salida=reply,
                    canal=Conversacion.CANAL_WHATSAPP,
                )
            _complete_message(processed)
            return JsonResponse({
                "ok": True,
                "stage8": True,
                "published": published,
                "sent": bool(send_result and send_result.sent),
            })
        if human_owned:
            Conversacion.objects.create(
                cliente=cliente,
                mensaje_entrada=message,
                mensaje_salida="",
                canal=Conversacion.CANAL_WHATSAPP,
            )
            _complete_message(processed)
            return JsonResponse({"ok": True, "human_takeover": True, "sent": None})

        v2_blocked = active_lead and getattr(active_lead, '_v2_blocked', False)

        if not bot_deberia_responder:
            if not active_lead:
                active_lead = Lead.objects.create(cliente=cliente, estado=Lead.NUEVO)
            fue_derivado = active_lead.requiere_asesor and not hasattr(active_lead, '_handoff_sent')

            # V2: one‑time message (only when V2 was the blocking reason)
            if v2_blocked:
                v2_msg_sent = Conversacion.objects.filter(
                    cliente=cliente,
                    mensaje_salida=MENSAJE_V2,
                ).exists()
                if not v2_msg_sent:
                    try:
                        _send_bot_message(phone, MENSAJE_V2, channel, canonical_conversation)
                        Conversacion.objects.create(
                            cliente=cliente,
                            mensaje_entrada="",
                            mensaje_salida=MENSAJE_V2,
                            canal=Conversacion.CANAL_WHATSAPP,
                        )
                        logger.info(
                            "[ConversationGuardV2]\nlead_id=%d\nmensaje=enviado",
                            active_lead.id,
                        )
                    except Exception:
                        logger.warning(
                            "No se pudo enviar mensaje V2 para lead %d", active_lead.id,
                        )

            Conversacion.objects.create(
                cliente=cliente,
                mensaje_entrada=message,
                mensaje_salida="",
                canal=Conversacion.CANAL_WHATSAPP,
            )
            if fue_derivado:
                _send_handoff_message(phone, active_lead, channel, canonical_conversation)
            _complete_message(processed)
            return JsonResponse({"ok": True, "human_takeover": True, "sent": None})

        # Conversation Guard — detecta si el lead ya está siendo atendido
        # por un asesor desde WhatsApp Business (mensajes no visibles para el sistema)
        guard = should_bot_handle_lead(lead=active_lead, incoming_message=message)
        if not guard["allow_bot"]:
            if active_lead and guard["pause_bot"] and not active_lead.atencion_humana:
                active_lead.atencion_humana = True
                active_lead.bot_pausado = True
                save_fields = ["atencion_humana", "bot_pausado"]
                if guard.get("reason") == "posible_conversacion_humana_por_whatsapp_business":
                    active_lead.motivo_derivacion = "Posible conversación activa por WhatsApp Business"
                    save_fields.append("motivo_derivacion")
                    active_lead.fecha_derivacion = timezone.now()
                    save_fields.append("fecha_derivacion")
                active_lead.save(update_fields=save_fields)
            if guard.get("message_to_client") and active_lead and not getattr(active_lead, '_guard_msg_sent', False):
                try:
                    _send_bot_message(phone, guard["message_to_client"], channel, canonical_conversation)
                    active_lead._guard_msg_sent = True
                except Exception:
                    logger.warning("No se pudo enviar mensaje de guard para lead %d", active_lead.id)
            Conversacion.objects.create(
                cliente=cliente,
                mensaje_entrada=message,
                mensaje_salida="",
                canal=Conversacion.CANAL_WHATSAPP,
            )
            _complete_message(processed)
            return JsonResponse({"ok": True, "human_takeover": True, "sent": None})

        reply = handle_incoming_message(cliente, message)

        if active_lead and not active_lead.requiere_asesor:
            try:
                conf = ConfiguracionBot.obtener(channel=channel)
                if conf.modo_operacion == "recopilar":
                    active_lead.refresh_from_db()
                    if active_lead.precio_recomendado or active_lead.precio_cotizado:
                        _marcar_derivacion(active_lead, ["Ficha completada en modo recopilar datos"])
                if conf.modo_atencion == "mixto" and active_lead.lista_objetos:
                    evaluation = evaluar_mixto_inteligente(active_lead)
                    if evaluation["requiere_asesor"]:
                        _marcar_derivacion(active_lead, evaluation["motivos"])
            except Exception:
                logger.warning("Error en re-evaluación mixto inteligente", exc_info=True)

        if active_lead and active_lead.requiere_asesor:
            _send_handoff_message(phone, active_lead, channel, canonical_conversation)
            _complete_message(processed)
            return JsonResponse({"ok": True, "human_takeover": True, "sent": None})

        send_result = _send_bot_message(phone, reply, channel, canonical_conversation)
        if not _message_was_sent(send_result):
            raise WhatsappSendError("Meta no acepto la respuesta saliente.")
        Conversacion.objects.create(
            cliente=cliente,
            mensaje_entrada=message,
            mensaje_salida=reply,
            canal=Conversacion.CANAL_WHATSAPP,
        )
        _complete_message(processed)
        return JsonResponse({"ok": True, "sent": send_result})
    except Exception:
        logger.exception("Error procesando mensaje entrante.")
        if processed:
            processed.delete()
        return JsonResponse({"ok": False, "error": "processing_error"}, status=500)


MENSAJE_V2 = "Tu consulta será revisada por un asesor."

MENSAJE_DERIVACION = (
    "Gracias, ya tengo los datos principales. "
    "Por las características del servicio, un asesor revisará tu caso "
    "para darte una cotización precisa."
)


def _send_bot_message(phone, body, channel, conversation):
    return send_whatsapp_message(
        phone,
        body,
        channel=channel,
        author_type=AuthorType.BOT if conversation else None,
        conversation_id=conversation.id if conversation else None,
    )


def _send_handoff_message(phone, lead, channel=None, conversation=None):
    if getattr(lead, '_handoff_sent', False):
        return
    try:
        _send_bot_message(phone, MENSAJE_DERIVACION, channel, conversation)
        lead._handoff_sent = True
        logger.info(
            "Mensaje de derivación enviado a %s para lead %d", phone, lead.id,
        )
    except Exception as e:
        logger.warning("No se pudo enviar mensaje de derivación: %s", e)


def _marcar_atencion_humana(lead):
    if not lead.atencion_humana:
        lead.atencion_humana = True
        lead.save(update_fields=["atencion_humana"])


def _active_lead(cliente):
    return (
        cliente.leads.exclude(estado__in=[Lead.CERRADO, Lead.PERDIDO])
        .order_by("-fecha_creacion")
        .first()
    )


def _lead_for_image(cliente, active_lead):
    if not active_lead:
        return None
    latest_conversation = cliente.conversaciones.order_by("-fecha").first()
    is_stale = (
        latest_conversation
        and timezone.now() - latest_conversation.fecha > timedelta(minutes=45)
    )
    has_previous_quote = bool(
        active_lead.estado == Lead.COTIZADO
        or active_lead.precio_recomendado is not None
    )
    if is_stale and has_previous_quote:
        return Lead.objects.create(cliente=cliente, estado=Lead.NUEVO)
    return active_lead


def _reserve_message(event):
    message_id = event.get("message_id", "")
    if not message_id:
        return None
    processed, created = MensajeWhatsappProcesado.objects.get_or_create(
        message_id=message_id,
        defaults={
            "telefono": event.get("phone", ""),
            "tipo": event.get("type", ""),
        },
    )
    if not created:
        return False
    return processed


def _complete_message(processed):
    if not processed:
        return
    processed.completado = True
    processed.save(update_fields=["completado"])


def _message_was_sent(result):
    return bool(
        isinstance(result, dict)
        and result.get("messages")
        and result["messages"][0].get("id")
    )


class WhatsappSendError(Exception):
    pass


def _receive_image(cliente, active_lead, event):
    lead = active_lead or Lead.objects.create(cliente=cliente, estado=Lead.NUEVO)
    canonical_conversation = obtener_o_crear_conversacion(lead)
    control, _ = ConversationControl.objects.get_or_create(conversation=canonical_conversation)
    download_result = download_whatsapp_image(cliente, lead, event)
    caption = event.get("caption", "").strip()
    incoming_label = "[Foto recibida]"
    if caption:
        incoming_label += f" {caption}"

    if (
        lead.atencion_humana
        or canonical_conversation.estado_atencion == canonical_conversation.ATENCION_ASESOR
        or canonical_conversation.bot_pausado
        or control.owner_state == OwnerState.AGENT_ACTIVE
    ):
        Conversacion.objects.create(
            cliente=cliente,
            mensaje_entrada=incoming_label,
            mensaje_salida="",
            canal=Conversacion.CANAL_WHATSAPP,
        )
        return JsonResponse(
            {
                "ok": True,
                "human_takeover": True,
                "media_saved": download_result.get("saved", False),
            }
        )

    if caption:
        reply = handle_incoming_message(cliente, caption)
    else:
        evidence = download_result.get("evidence")
        analysis = analyze_moving_image(evidence)
        if analysis:
            evidence.analisis_visual = analysis.get("resumen") or ", ".join(
                analysis.get("objetos", [])
            )
            evidence.save(update_fields=["analisis_visual"])
            reply = handle_image_inventory(cliente, analysis)
        else:
            next_question = next_missing_question_for(cliente)
            reply = (
                "Gracias, ya recibi la foto y la deje adjunta a tu cotizacion. "
                "Todavia necesito confirmar el inventario antes de calcular el precio."
            )
            if next_question and "cosas" not in next_question.lower():
                reply = f"{reply} {next_question}"

    send_result = _send_bot_message(
        cliente.telefono, reply, canonical_conversation.channel, canonical_conversation
    )
    if not _message_was_sent(send_result):
        raise WhatsappSendError("Meta no acepto la respuesta a la imagen.")
    Conversacion.objects.create(
        cliente=cliente,
        mensaje_entrada=incoming_label,
        mensaje_salida=reply,
        canal=Conversacion.CANAL_WHATSAPP,
    )
    return JsonResponse(
        {
            "ok": True,
            "media_saved": download_result.get("saved", False),
            "media_reason": download_result.get("reason", ""),
            "sent": send_result,
        }
    )

@require_http_methods(["GET", "PATCH"])
def bot_settings(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "authentication_required"}, status=403)
    if settings.STRICT_ADMIN_OPERATIONS and request.method != "GET" and not (request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()):
        return JsonResponse({"error": "permission_denied"}, status=403)
    channel_id = request.GET.get("channel")
    channel = None
    if channel_id:
        channel = WhatsAppChannel.objects.filter(id=channel_id).first()
    conf = ConfiguracionBot.obtener(channel=channel)
    if request.method == "GET":
        filters = {}
        if channel:
            filters["channel"] = channel
        schedules = BotSchedule.objects.filter(**filters).order_by("day_of_week", "start_time")
        return JsonResponse({
            "bot_activo": conf.bot_activo,
            "modo_atencion": conf.modo_atencion,
            "modo_operacion": conf.modo_operacion,
            "zona_horaria": conf.zona_horaria,
            "transferir_fuera_horario": conf.transferir_fuera_horario,
            "confianza_minima": float(conf.confianza_minima),
            "margen_minimo_porcentaje": float(conf.margen_minimo_porcentaje),
            "espera_asesor_minutos": conf.espera_asesor_minutos,
            "seguimiento_horas": conf.seguimiento_horas,
            "asesor_predeterminado_id": conf.asesor_predeterminado_id,
            "reglas_automaticas": conf.reglas_automaticas,
            "mensaje_bienvenida": conf.mensaje_bienvenida,
            "hora_inicio_bot": conf.hora_inicio_bot.strftime("%H:%M") if hasattr(conf.hora_inicio_bot, "strftime") else str(conf.hora_inicio_bot or ""),
            "hora_fin_bot": conf.hora_fin_bot.strftime("%H:%M") if hasattr(conf.hora_fin_bot, "strftime") else str(conf.hora_fin_bot or ""),
            "lunes_activo": conf.lunes_activo,
            "martes_activo": conf.martes_activo,
            "miercoles_activo": conf.miercoles_activo,
            "jueves_activo": conf.jueves_activo,
            "viernes_activo": conf.viernes_activo,
            "sabado_activo": conf.sabado_activo,
            "domingo_activo": conf.domingo_activo,
            "mensaje_fuera_horario": conf.mensaje_fuera_horario,
            "override_activo": conf.override_activo,
            "override_modo": conf.override_modo,
            "override_desde": conf.override_desde.isoformat() if conf.override_desde else None,
            "override_hasta": conf.override_hasta.isoformat() if conf.override_hasta else None,
            "override_motivo": conf.override_motivo,
            "modos_atencion": [
                {"value": v, "label": l}
                for v, l in whatsapp_models.MODO_ATENCION_CHOICES
            ],
            "override_modos": [
                {"value": v, "label": l}
                for v, l in whatsapp_models.OVERRIDE_MODO_CHOICES
            ],
            "dias_semana": [
                {"value": v, "label": l}
                for v, l in whatsapp_models.DIAS_SEMANA
            ],
            "schedules": [
                {
                    "id": s.id,
                    "day_of_week": s.day_of_week,
                    "start_time": s.start_time.strftime("%H:%M") if hasattr(s.start_time, "strftime") else str(s.start_time or ""),
                    "end_time": s.end_time.strftime("%H:%M") if hasattr(s.end_time, "strftime") else str(s.end_time or ""),
                    "is_active": s.is_active,
                    "modo": s.modo,
                }
                for s in schedules
            ],
            "canales": [
                {"id": ch.id, "nombre": str(ch)}
                for ch in WhatsAppChannel.objects.filter(activo=True)
            ],
            "channel_id": channel.id if channel else None,
        })

    data = json.loads(request.body)
    if "modo_operacion" in data and data["modo_operacion"] in dict(whatsapp_models.MODOS_OPERACION):
        conf.modo_operacion = data["modo_operacion"]
        legacy = {
            "asesor": ("humano", False),
            "recopilar": ("bot", True),
            "automatica": ("bot", True),
            "hibrido": ("mixto", True),
        }[conf.modo_operacion]
        conf.modo_atencion, conf.bot_activo = legacy
    for field in [
        "bot_activo", "modo_atencion",
        "lunes_activo", "martes_activo", "miercoles_activo",
        "jueves_activo", "viernes_activo", "sabado_activo", "domingo_activo",
        "mensaje_fuera_horario",
        "override_activo", "override_modo", "override_motivo",
    ]:
        if field in data:
            setattr(conf, field, data[field])
    if "modo_atencion" in data and "modo_operacion" not in data:
        conf.modo_operacion = {"humano": "asesor", "bot": "automatica", "mixto": "hibrido"}.get(conf.modo_atencion, "automatica")
    if "hora_inicio_bot" in data:
        conf.hora_inicio_bot = datetime.strptime(data["hora_inicio_bot"], "%H:%M").time()
    if "hora_fin_bot" in data:
        conf.hora_fin_bot = datetime.strptime(data["hora_fin_bot"], "%H:%M").time()
    if "override_desde" in data and data["override_desde"]:
        conf.override_desde = datetime.fromisoformat(data["override_desde"])
    if "override_hasta" in data and data["override_hasta"]:
        conf.override_hasta = datetime.fromisoformat(data["override_hasta"])
    if "override_desde" in data and data["override_desde"] is None:
        conf.override_desde = None
    if "override_hasta" in data and data["override_hasta"] is None:
        conf.override_hasta = None
    conf.save()
    logger.info("ConfiguracionBot actualizada por %s", request.user)
    return JsonResponse({"ok": True})


def _schedule_overlaps(channel, day_of_week, modo, start_time, end_time, exclude_id=None):
    qs = BotSchedule.objects.filter(
        channel=channel,
        day_of_week=day_of_week,
        modo=modo,
        start_time__lt=end_time,
        end_time__gt=start_time,
    )
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    return qs.exists()


@require_http_methods(["GET", "POST"])
def bot_schedules(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "authentication_required"}, status=403)
    if settings.STRICT_ADMIN_OPERATIONS and request.method != "GET" and not (request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()):
        return JsonResponse({"error": "permission_denied"}, status=403)
    channel_id = request.GET.get("channel")
    channel = None
    if channel_id:
        channel = WhatsAppChannel.objects.filter(id=channel_id).first()
    if request.method == "GET":
        filters = {}
        if channel:
            filters["channel"] = channel
        qs = BotSchedule.objects.filter(**filters).order_by("day_of_week", "start_time")
        return JsonResponse([
            {
                "id": s.id,
                "day_of_week": s.day_of_week,
                "start_time": s.start_time.strftime("%H:%M") if hasattr(s.start_time, "strftime") else str(s.start_time or ""),
                "end_time": s.end_time.strftime("%H:%M") if hasattr(s.end_time, "strftime") else str(s.end_time or ""),
                "is_active": s.is_active,
                "modo": s.modo,
            }
            for s in qs
        ], safe=False)
    data = json.loads(request.body)
    start_time = datetime.strptime(data["start_time"], "%H:%M").time()
    end_time = datetime.strptime(data["end_time"], "%H:%M").time()
    modo = data.get("modo", "bot")
    if _schedule_overlaps(channel, data["day_of_week"], modo, start_time, end_time):
        return JsonResponse({
            "error": "overlap",
            "message": "Ya existe un horario que se solapa con este rango para el mismo canal, día y modo.",
        }, status=400)
    schedule = BotSchedule.objects.create(
        channel=channel,
        day_of_week=data["day_of_week"],
        start_time=start_time,
        end_time=end_time,
        is_active=data.get("is_active", True),
        modo=modo,
    )
    logger.info("BotSchedule creado por %s: %s", request.user, schedule)
    return JsonResponse({
        "id": schedule.id,
        "day_of_week": schedule.day_of_week,
        "start_time": schedule.start_time.strftime("%H:%M") if hasattr(schedule.start_time, "strftime") else str(schedule.start_time or ""),
        "end_time": schedule.end_time.strftime("%H:%M") if hasattr(schedule.end_time, "strftime") else str(schedule.end_time or ""),
        "is_active": schedule.is_active,
        "modo": schedule.modo,
    }, status=201)


@require_http_methods(["GET", "POST"])
def whatsapp_channels(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "authentication_required"}, status=403)
    if settings.STRICT_ADMIN_OPERATIONS and request.method != "GET" and not (request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()):
        return JsonResponse({"error": "permission_denied"}, status=403)
    if request.method == "GET":
        qs = WhatsAppChannel.objects.all().order_by("nombre")
        filtro = request.GET.get("filter", "all")
        if filtro == "active":
            qs = qs.filter(activo=True)
        elif filtro == "inactive":
            qs = qs.filter(activo=False)
        return JsonResponse([
            {
                "id": ch.id,
                "nombre": ch.nombre,
                "phone_number_id": ch.phone_number_id,
                "numero_visible": ch.numero_visible,
                "asesor_id": ch.asesor_id,
                "asesor_nombre": str(ch.asesor) if ch.asesor else "",
                "activo": ch.activo,
                "lead_count": ch.leads.count(),
            }
            for ch in qs
        ], safe=False)
    data = json.loads(request.body)
    logger.info("WhatsApp channel create requested (actor_id=%s).", request.user.id)
    asesor_id = data.get("asesor_id")
    if asesor_id == "" or asesor_id is None:
        asesor_id = None
    channel = WhatsAppChannel.objects.create(
        nombre=data.get("nombre", ""),
        phone_number_id=data.get("phone_number_id", ""),
        numero_visible=data.get("numero_visible", ""),
        asesor_id=asesor_id,
        activo=data.get("activo", True),
    )
    logger.info("WhatsAppChannel creado por %s: %s", request.user, channel.nombre)
    return JsonResponse({
        "id": channel.id,
        "nombre": channel.nombre,
        "phone_number_id": channel.phone_number_id,
        "numero_visible": channel.numero_visible,
        "asesor_id": channel.asesor_id,
        "asesor_nombre": str(channel.asesor) if channel.asesor else "",
        "activo": channel.activo,
    }, status=201)


@require_http_methods(["PATCH", "DELETE"])
def whatsapp_channel_detail(request, channel_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "authentication_required"}, status=403)
    if settings.STRICT_ADMIN_OPERATIONS and not (request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()):
        return JsonResponse({"error": "permission_denied"}, status=403)
    try:
        channel = WhatsAppChannel.objects.get(id=channel_id)
    except WhatsAppChannel.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)

    if request.method == "DELETE":
        lead_count = channel.leads.count()
        config_count = ConfiguracionBot.objects.filter(channel=channel).count()
        schedule_count = BotSchedule.objects.filter(channel=channel).count()
        from apps.clientes.models import Conversacion
        from apps.leads.models import Lead
        conv_count = Conversacion.objects.filter(
            cliente__in=Lead.objects.filter(whatsapp_channel=channel).values("cliente")
        ).count()
        has_history = lead_count > 0 or config_count > 0 or schedule_count > 0 or conv_count > 0
        if has_history:
            logger.warning(
                "Eliminación bloqueada para canal %d (%s): leads=%d configs=%d schedules=%d conversaciones=%d",
                channel_id, channel.nombre, lead_count, config_count, schedule_count, conv_count,
            )
            return JsonResponse({
                "ok": False,
                "error": "has_history",
                "message": "Este canal tiene información histórica asociada. Se recomienda desactivarlo.",
                "details": {
                    "lead_count": lead_count,
                    "config_count": config_count,
                    "schedule_count": schedule_count,
                    "conversacion_count": conv_count,
                },
            }, status=409)
        channel.delete()
        logger.info("WhatsAppChannel %d eliminado por %s", channel_id, request.user)
        return JsonResponse({"ok": True, "deleted": True})

    data = json.loads(request.body)
    logger.info("WhatsApp channel update requested (channel_id=%s, actor_id=%s).", channel_id, request.user.id)
    errors = {}
    if "nombre" in data:
        if not data["nombre"]:
            errors["nombre"] = "El nombre es obligatorio."
        else:
            channel.nombre = data["nombre"]
    if "phone_number_id" in data:
        if not data["phone_number_id"]:
            errors["phone_number_id"] = "El Phone Number ID es obligatorio."
        else:
            duplicate = WhatsAppChannel.objects.filter(phone_number_id=data["phone_number_id"]).exclude(id=channel_id).first()
            if duplicate:
                errors["phone_number_id"] = "Ya existe otro canal con ese Phone Number ID."
            else:
                channel.phone_number_id = data["phone_number_id"]
    if "numero_visible" in data:
        channel.numero_visible = data["numero_visible"]
    if "asesor_id" in data:
        raw = data["asesor_id"]
        channel.asesor_id = raw if raw not in (None, "", 0) else None
    if "activo" in data:
        channel.activo = data["activo"]
    if errors:
        logger.warning("Error validando canal %d: %s", channel_id, errors)
        return JsonResponse({"ok": False, "errors": errors}, status=400)
    channel.save()
    logger.info("WhatsAppChannel %d actualizado por %s", channel_id, request.user)
    return JsonResponse({
        "ok": True,
        "channel": {
            "id": channel.id,
            "nombre": channel.nombre,
            "phone_number_id": channel.phone_number_id,
            "numero_visible": channel.numero_visible,
            "asesor_id": channel.asesor_id,
            "asesor_nombre": str(channel.asesor) if channel.asesor else "",
            "activo": channel.activo,
            "lead_count": channel.leads.count(),
        }
    })


@require_http_methods(["GET"])
def whatsapp_channel_asesores(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "authentication_required"}, status=403)
    if settings.STRICT_ADMIN_OPERATIONS and not (request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()):
        return JsonResponse({"error": "permission_denied"}, status=403)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    users = User.objects.all().order_by("username")
    return JsonResponse([
        {"id": u.id, "username": u.username}
        for u in users
    ], safe=False)


@require_http_methods(["PATCH", "DELETE"])
def bot_schedule_detail(request, schedule_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "authentication_required"}, status=403)
    if settings.STRICT_ADMIN_OPERATIONS and not (request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()):
        return JsonResponse({"error": "permission_denied"}, status=403)
    try:
        schedule = BotSchedule.objects.get(id=schedule_id)
    except BotSchedule.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)
    if request.method == "DELETE":
        schedule.delete()
        logger.info("BotSchedule %d eliminado por %s", schedule_id, request.user)
        return JsonResponse({"ok": True}, status=204)
    data = json.loads(request.body)
    day_of_week = data.get("day_of_week", schedule.day_of_week)
    start_time = datetime.strptime(data["start_time"], "%H:%M").time() if "start_time" in data else schedule.start_time
    end_time = datetime.strptime(data["end_time"], "%H:%M").time() if "end_time" in data else schedule.end_time
    modo = data.get("modo", schedule.modo)
    channel = schedule.channel
    if _schedule_overlaps(channel, day_of_week, modo, start_time, end_time, exclude_id=schedule.id):
        return JsonResponse({
            "error": "overlap",
            "message": "Ya existe un horario que se solapa con este rango para el mismo canal, día y modo.",
        }, status=400)
    if "day_of_week" in data:
        schedule.day_of_week = data["day_of_week"]
    if "start_time" in data:
        schedule.start_time = start_time
    if "end_time" in data:
        schedule.end_time = end_time
    if "is_active" in data:
        schedule.is_active = data["is_active"]
    if "modo" in data:
        schedule.modo = data["modo"]
    schedule.save()
    logger.info("BotSchedule %d actualizado por %s", schedule_id, request.user)
    return JsonResponse({
        "id": schedule.id,
        "day_of_week": schedule.day_of_week,
        "start_time": schedule.start_time.strftime("%H:%M"),
        "end_time": schedule.end_time.strftime("%H:%M"),
        "is_active": schedule.is_active,
        "modo": schedule.modo,
    })
