from django.shortcuts import redirect
from django.urls import include, path

from apps.campo.views import pizarra

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
)

def dashboard_redirect(request):
    if request.user.is_authenticated:
        return redirect("dashboard-leads")
    else:
        return redirect("dashboard-login")

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
    path("canales-whatsapp/", placeholder_canales, name="dashboard-canales"),
    path("admin/", placeholder_admin, name="dashboard-admin-placeholder"),
]

