from django.urls import path

from . import views

urlpatterns = [
    # Vehículos
    path("vehiculos/", views.vehiculo_list, name="dashboard-flota-vehiculos"),
    path("vehiculos/nuevo/", views.vehiculo_create, name="flota-vehiculo-create"),
    path("vehiculos/<int:pk>/", views.vehiculo_detail, name="flota-vehiculo-detail"),
    path("vehiculos/<int:pk>/editar/", views.vehiculo_edit, name="flota-vehiculo-edit"),
    path("vehiculos/<int:pk>/toggle/", views.vehiculo_toggle, name="flota-vehiculo-toggle"),
    # Mantenimientos
    path("mantenimientos/", views.mantenimiento_list, name="dashboard-flota-mantenimientos"),
    path("mantenimientos/nuevo/", views.mantenimiento_create, name="flota-mantenimiento-create"),
    path("mantenimientos/<int:pk>/editar/", views.mantenimiento_edit, name="flota-mantenimiento-edit"),
    path("mantenimientos/<int:pk>/eliminar/", views.mantenimiento_delete, name="flota-mantenimiento-delete"),
]
