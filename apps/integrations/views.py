from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .providers.chatwoot.webhook import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    parse_payload,
    process_webhook,
    verify_signature,
)


@csrf_exempt
@require_POST
def chatwoot_webhook(request):
    if not settings.CHATWOOT_WEBHOOK_ENABLED:
        return JsonResponse({"detail": "Not found."}, status=404)
    if request.content_type != "application/json":
        return JsonResponse({"detail": "Content-Type must be application/json."}, status=415)
    raw_body = request.body
    try:
        verify_signature(
            raw_body,
            request.headers.get("X-Chatwoot-Timestamp"),
            request.headers.get("X-Chatwoot-Signature"),
        )
        payload = parse_payload(raw_body)
        result = process_webhook(payload, request.headers.get("X-Chatwoot-Delivery", ""))
    except InvalidWebhookSignature:
        return JsonResponse({"detail": "Invalid webhook signature."}, status=401)
    except InvalidWebhookPayload as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse({
        "status": "ok",
        "classification": result.classification,
        "action": result.action,
        "duplicate": result.duplicate,
    })
