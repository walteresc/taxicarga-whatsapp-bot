from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.dashboard.permissions import has_role


@login_required
def sidebar(request):
    user = request.user
    user_groups = [group.name for group in user.groups.all()]

    menu_items = [
        {"path": "/dashboard/leads/", "icon": "mdi-account", "title": "Leads", "roles": ["Administrador", "Supervisor", "Asesor de Ventas"]},
        {"path": "/dashboard/servicios/", "icon": "mdi-truck-check", "title": "Reservas", "roles": ["Administrador", "Supervisor", "Asesor de Ventas"]},
        {"path": "/dashboard/pizarra/", "icon": "mdi-view-week", "title": "Pizarra", "roles": ["Administrador", "Supervisor", "Asesor de Ventas"]},
        {"path": "/dashboard/campo/conductores/", "icon": "mdi-steering", "title": "Conductores", "roles": ["Administrador", "Supervisor", "Asesor de Ventas"]},
        {"path": "/dashboard/campo/ayudantes/", "icon": "mdi-account-hard-hat", "title": "Ayudantes", "roles": ["Administrador", "Supervisor", "Asesor de Ventas"]},
        {"path": "/dashboard/campo/equipos/", "icon": "mdi-account-group", "title": "Equipos de Campo", "roles": ["Administrador", "Supervisor", "Asesor de Ventas"]},
        {"path": "/dashboard/flota/vehiculos/", "icon": "mdi-truck", "title": "Vehículos", "roles": ["Administrador", "Supervisor", "Asesor de Ventas"]},
        {"path": "/dashboard/flota/mantenimientos/", "icon": "mdi-book-open-page-variant", "title": "Mantenimientos", "roles": ["Administrador", "Supervisor", "Asesor de Ventas"]},
        {"path": "/dashboard/whatsapp/", "icon": "mdi-chat", "title": "Bot WhatsApp", "roles": ["Administrador", "Supervisor", "Asesor de Ventas"]},
        {"path": "/dashboard/canales-whatsapp/", "icon": "mdi-phone", "title": "Canales WhatsApp", "roles": ["Administrador", "Supervisor", "Asesor de Ventas"]},
        {"path": "/dashboard/reportes/", "icon": "mdi-chart-bar", "title": "Reportes", "roles": ["Administrador", "Supervisor"]},
        {"path": "/dashboard/mis-servicios/", "icon": "mdi-truck-delivery", "title": "Mis Servicios", "roles": ["Conductor", "Ayudante"]},
        {"path": "/dashboard/mi-programacion/", "icon": "mdi-calendar-clock", "title": "Mi Programación", "roles": ["Conductor", "Ayudante"]}
    ]

    visible_items = [item for item in menu_items if any(role in user_groups for role in item["roles"])]

    return render(request, "dashboard/sidebar.html", {"menu_items": visible_items})
