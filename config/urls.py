"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from apps.whatsapp.views import bot_schedules, bot_schedule_detail, bot_settings, whatsapp_channels, whatsapp_channel_detail, whatsapp_channel_asesores

urlpatterns = [
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
]
