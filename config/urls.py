from django.contrib import admin
from django.urls import include, path, re_path
from apps.whatsapp.views import bot_schedules, bot_schedule_detail, bot_settings, whatsapp_channels, whatsapp_channel_detail, whatsapp_channel_asesores
from apps.whatsapp.views_media import media_proxy
from django.shortcuts import redirect
from django.conf import settings
from django.views.decorators.cache import never_cache
from apps.dashboard.views_spa import spa_fallback
from .health import live, ready

def root_redirect(request, *args, **kwargs):
    # Si no está autenticado, redirigir a login
    if not request.user.is_authenticated:
        return redirect("dashboard-login")
    # Si está autenticado, ir a bandeja
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
    path("media/proxy/<str:media_id>/", media_proxy, name="media-proxy"),
    path("webhooks/chatwoot/", include("apps.integrations.urls")),
    path("webhooks/", include("apps.whatsapp_bot_v4.urls")),

    # SPA fallback: serve index.html for all other routes (but not API/admin/static/media)
    # In production (Docker): Nginx handles /static/ and /media/
    # In development: StaticFilesHandler handles /static/ and /media/
    # Must be LAST because it's a catch-all
    re_path(r"^(?!admin/|api/|webhooks/|webhook/|dashboard/|static/|media/|health/).+$", never_cache(spa_fallback)),
]
