from django.shortcuts import redirect
from django.urls import include, path

from apps.campo.views import pizarra
from .views_whatsapp import whatsapp_conversacion_accion, whatsapp_conversaciones
from .views_quotes import whatsapp_crear_cotizacion, whatsapp_por_cotizar, whatsapp_solicitud_accion
from .views_quote_history import whatsapp_cotizacion_accion, whatsapp_cotizacion_detalle, whatsapp_cotizaciones
from .views_bot_config import whatsapp_configuracion as whatsapp_configuracion_v2

from .views import (
    create_lead,
    dashboard_home,
    dashboard_logout,
    export_leads_csv,
    lead_action,
    login_view,
    placeholder_admin,
    placeholder_canales,
    placeholder_reportes,
    placeholder_whatsapp,
    whatsapp_configuracion,
    whatsapp_conversaciones_base,
)

def dashboard_redirect(request):
    if request.user.is_authenticated and request.GET.get("channel"):
        return dashboard_home(request)
    return redirect("dashboard-leads")

urlpatterns = [
    path("login/", login_view, name="dashboard-login"),
    path("logout/", dashboard_logout, name="dashboard-logout"),
    path("", dashboard_redirect, name="dashboard-home"),
    path("leads/", dashboard_home, name="dashboard-leads"),
    path("leads/nuevo/", create_lead, name="dashboard-lead-create"),
    path("leads/<int:lead_id>/", dashboard_home, name="dashboard-lead-detail"),
    path("leads/<int:lead_id>/accion/", lead_action, name="dashboard-lead-action"),
    path("servicios/", include("apps.servicios.urls")),
    path("clientes/", include("apps.clientes.urls_dashboard")),
    path("pizarra/", pizarra, name="dashboard-pizarra"),
    path("campo/", include("apps.campo.urls")),
    path("flota/", include("apps.flota.urls")),
    path("exportar/leads.csv", export_leads_csv, name="dashboard-leads-export"),
    path("reportes/", placeholder_reportes, name="dashboard-reportes"),
    path("whatsapp/", placeholder_whatsapp, name="dashboard-whatsapp"),
    path("whatsapp/conversaciones/", whatsapp_conversaciones, name="dashboard-whatsapp-conversaciones"),
    path("whatsapp/conversaciones/<int:conversation_id>/accion/", whatsapp_conversacion_accion, name="dashboard-whatsapp-conversacion-accion"),
    path("whatsapp/por-cotizar/", whatsapp_por_cotizar, name="dashboard-whatsapp-por-cotizar"),
    path("whatsapp/por-cotizar/<int:request_id>/accion/", whatsapp_solicitud_accion, name="dashboard-whatsapp-solicitud-accion"),
    path("whatsapp/por-cotizar/<int:request_id>/crear/", whatsapp_crear_cotizacion, name="dashboard-whatsapp-crear-cotizacion"),
    path("whatsapp/cotizaciones/", whatsapp_cotizaciones, name="dashboard-whatsapp-cotizaciones"),
    path("whatsapp/cotizaciones/<int:quote_id>/accion/", whatsapp_cotizacion_accion, name="dashboard-whatsapp-cotizacion-accion"),
    path("whatsapp/cotizaciones/<int:quote_id>/", whatsapp_cotizacion_detalle, name="dashboard-whatsapp-cotizacion-detalle"),
    path("whatsapp/configuracion/", whatsapp_configuracion_v2, name="dashboard-whatsapp-configuracion"),
    path("canales-whatsapp/", placeholder_canales, name="dashboard-canales"),
    path("admin/", placeholder_admin, name="dashboard-admin-placeholder"),
]

