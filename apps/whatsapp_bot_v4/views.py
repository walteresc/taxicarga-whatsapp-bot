import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .adapters.chatwoot import ChatwootV4Adapter
from .adapters.crm import CRMV4Adapter
from .adapters.meta import MetaPayloadError, MetaV4Adapter
from .ai.agent import OpenAIConversationAgent
from .repositories.state import DjangoBotStateRepository
from .services.conversation_service import ConversationService
from .services.meta_webhook_service import MetaWebhookV4Service
from .services.persistent_conversation_service import PersistentConversationService
from .services.quote_bridge import QuoteBridge


def build_meta_webhook_service():
    chatwoot = ChatwootV4Adapter()
    persistent = PersistentConversationService(
        ConversationService(OpenAIConversationAgent()),
        DjangoBotStateRepository(),
        crm_adapter=CRMV4Adapter(),
        chatwoot_adapter=chatwoot,
        quote_bridge=QuoteBridge(),
    )
    return MetaWebhookV4Service(
        meta_adapter=MetaV4Adapter(),
        persistent_service=persistent,
        chatwoot_adapter=chatwoot,
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def meta_webhook_v4(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge", "")
        if mode == "subscribe" and token and token == settings.WHATSAPP_VERIFY_TOKEN:
            return HttpResponse(challenge)
        return HttpResponse("verification failed", status=403)
    try:
        payload = json.loads(request.body or b"{}")
        result = build_meta_webhook_service().process_payload(payload)
    except (json.JSONDecodeError, MetaPayloadError) as exc:
        return JsonResponse({"status": "invalid", "error": exc.__class__.__name__}, status=400)
    return JsonResponse({"status": result.status})
