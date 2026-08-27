from django.urls import path

from .views import meta_webhook_v4
from .services.ycloud_webhook_service import ycloud_webhook
from .webhook_diagnostic import ycloud_webhook_diagnostic
from . import api_conversation_control
from .views_bot_control import bot_control_panel


urlpatterns = [
    path("", meta_webhook_v4, name="meta-webhook-v4"),
    path("ycloud/v1/", ycloud_webhook, name="ycloud-webhook-v1"),
    path("ycloud/v1/diagnostic/", ycloud_webhook_diagnostic, name="ycloud-webhook-diagnostic"),
    # Panel de control
    path("control-panel/", bot_control_panel, name="bot-control-panel"),
    # Conversation control API
    path("api/control/transfer-to-advisor/", api_conversation_control.transfer_to_advisor, name="transfer-to-advisor"),
    path("api/control/return-to-bot/", api_conversation_control.return_to_bot, name="return-to-bot"),
    path("api/control/advisor-detected/", api_conversation_control.advisor_detected, name="advisor-detected"),
    path("api/control/transaction-completed/", api_conversation_control.transaction_completed, name="transaction-completed"),
    path("api/control/transaction-cancelled/", api_conversation_control.transaction_cancelled, name="transaction-cancelled"),
    # Global bot control
    path("api/control/pause-global/", api_conversation_control.pause_global, name="pause-global"),
    path("api/control/activate-global/", api_conversation_control.activate_global, name="activate-global"),
    path("api/control/bot-status/", api_conversation_control.get_bot_status, name="bot-status"),
    path("api/control/conversations/", api_conversation_control.get_active_conversations, name="active-conversations"),
]
