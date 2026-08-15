from django.contrib import admin
from django.urls import include, path
from apps.whatsapp.views import bot_schedules, bot_schedule_detail, bot_settings, whatsapp_channels, whatsapp_channel_detail, whatsapp_channel_asesores
from django.shortcuts import redirect
from .health import live, ready

def root_redirect(request, *args, **kwargs):
    return redirect("dashboard-home")

urlpatterns = [
    path("", root_redirect, name="root_redirect"),
    path("health/live", live, name="health-live"),
    path("health/ready", ready, name="health-ready"),
    path("admin/", admin.site.urls),
    path("dashboard/", include("apps.dashboard.urls")),
    path("api/clientes/", include("apps.clientes.urls")),
    path("api/leads/", include("apps.leads.urls")),
    path("api/cotizador/", include("apps.cotizador.urls")),
    path("api/bot-settings/", bot_settings, name="api-bot-settings"),
    path("api/bot-schedules/", bot_schedules, name="api-bot-schedules"),
    path("api/bot-schedules/<int:schedule_id>/", bot_schedule_detail, name="api-bot-schedule-detail"),
    path("api/whatsapp-channels/", whatsapp_channels, name="api-whatsapp-channels"),
    path("api/whatsapp-channels/asesores/", whatsapp_channel_asesores, name="api-whatsapp-channel-asesores"),
    path("api/whatsapp-channels/<int:channel_id>/", whatsapp_channel_detail, name="api-whatsapp-channel-detail"),
    path("webhook/whatsapp/", include("apps.whatsapp.urls")),
    path("webhooks/chatwoot/", include("apps.integrations.urls")),
    path("webhooks/whatsapp/v4/", include("apps.whatsapp_bot_v4.urls")),
]
