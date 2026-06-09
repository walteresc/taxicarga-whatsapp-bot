from django.urls import path

from .views import create_lead, dashboard_home, dashboard_logout, export_leads_csv, lead_action, login_view

urlpatterns = [
    path("login/", login_view, name="dashboard-login"),
    path("logout/", dashboard_logout, name="dashboard-logout"),
    path("", dashboard_home, name="dashboard-home"),
    path("exportar/leads.csv", export_leads_csv, name="dashboard-leads-export"),
    path("leads/nuevo/", create_lead, name="dashboard-lead-create"),
    path("leads/<int:lead_id>/", dashboard_home, name="dashboard-lead-detail"),
    path("leads/<int:lead_id>/accion/", lead_action, name="dashboard-lead-action"),
]
