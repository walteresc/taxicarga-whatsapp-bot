"""Diagnostic webhook endpoint for debugging signatures without validation."""
import json
import hashlib
import hmac
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import logging

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def ycloud_webhook_diagnostic(request):
    """
    Diagnostic-only endpoint that captures webhook details WITHOUT signature validation.
    Used for debugging mismatches between YCloud and server secrets.

    NOT FOR PRODUCTION — Use only for troubleshooting.
    """
    timestamp = request.headers.get('Ycloud-Signature', '').split(',')[0].replace('t=', '')
    signature_header = request.headers.get('Ycloud-Signature', 'MISSING')
    body = request.body

    # Calculate what we would expect with our secret
    from django.conf import settings
    secret = settings.YCLOUD_WEBHOOK_SECRET

    if timestamp and secret:
        signed_payload = timestamp.encode('ascii') + b'.' + body
        expected_digest = hmac.new(
            secret.encode('utf-8'),
            signed_payload,
            hashlib.sha256
        ).hexdigest()
    else:
        expected_digest = "UNABLE_TO_CALCULATE"

    # Log everything
    diagnostic = {
        "timestamp": timestamp,
        "signature_header": signature_header[:50] + "...",
        "body_size": len(body),
        "body_hash": hashlib.sha256(body).hexdigest()[:16],
        "expected_hmac_with_our_secret": expected_digest[:16] + "...",
        "our_secret_length": len(secret),
        "our_secret_hash": hashlib.sha256(secret.encode()).hexdigest()[:8],
        "body_preview": body[:100].decode('utf-8', errors='replace'),
    }

    logger.warning(f"[DIAGNOSTIC] Webhook capture: {json.dumps(diagnostic)}")
    print(f"[DIAGNOSTIC] {json.dumps(diagnostic, indent=2)}")

    return JsonResponse({
        "status": "diagnostic_received",
        "note": "This endpoint captures data for debugging without validating signatures"
    }, status=200)
