import json
import logging
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.clientes.models import Cliente, Conversacion
from apps.ia.conversation_engine import (
    handle_image_inventory,
    handle_incoming_message,
    next_missing_question_for,
)
from apps.ia.image_analyzer import analyze_moving_image
from apps.leads.models import Lead

from .models import MensajeWhatsappProcesado
from .services import download_whatsapp_image, send_whatsapp_message
from .utils import extract_event

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

    event = extract_event(payload)
    if not event or not event["phone"]:
        logger.info("Webhook sin mensaje procesable.")
        return JsonResponse({"ok": True, "ignored": True})

    processed = _reserve_message(event)
    if processed is False:
        return JsonResponse({"ok": True, "duplicate": True})

    phone = event["phone"]
    cliente, _ = Cliente.objects.get_or_create(telefono=phone)
    cliente.ultima_interaccion = timezone.now()
    cliente.save(update_fields=["ultima_interaccion"])

    try:
        active_lead = _active_lead(cliente)
        if event["type"] == "image":
            active_lead = _lead_for_image(cliente, active_lead)
            response = _receive_image(cliente, active_lead, event)
            _complete_message(processed)
            return response
        if event["type"] != "text" or not event["text"]:
            logger.info("Tipo de mensaje WhatsApp no procesable: %s", event["type"])
            _complete_message(processed)
            return JsonResponse({"ok": True, "ignored": True})

        message = event["text"]
        if active_lead and active_lead.atencion_humana:
            Conversacion.objects.create(
                cliente=cliente,
                mensaje_entrada=message,
                mensaje_salida="",
                canal=Conversacion.CANAL_WHATSAPP,
            )
            _complete_message(processed)
            return JsonResponse({"ok": True, "human_takeover": True, "sent": None})

        reply = handle_incoming_message(cliente, message)
        send_result = send_whatsapp_message(phone, reply)
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
    download_result = download_whatsapp_image(cliente, lead, event)
    caption = event.get("caption", "").strip()
    incoming_label = "[Foto recibida]"
    if caption:
        incoming_label += f" {caption}"

    if lead.atencion_humana:
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

    send_result = send_whatsapp_message(cliente.telefono, reply)
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

# Create your views here.
