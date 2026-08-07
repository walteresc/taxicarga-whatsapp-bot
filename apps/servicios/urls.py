from django.urls import path

from . import views

urlpatterns = [
    path("", views.lista_reservas, name="dashboard-servicios-list"),
    path("nuevo/", views.crear_reserva, name="dashboard-servicios-create"),
    path("buscar-clientes/", views.buscar_clientes, name="dashboard-servicios-buscar-clientes"),
    path("<int:pk>/", views.detalle_reserva, name="dashboard-servicios-detail"),
    path("<int:pk>/editar/", views.editar_reserva, name="dashboard-servicios-edit"),
    path("<int:pk>/finalizar/", views.finalizar_reserva, name="dashboard-servicios-finalizar"),
    path("<int:pk>/cancelar/", views.cancelar_reserva, name="dashboard-servicios-cancelar"),
    path("<int:pk>/pago/", views.registrar_pago, name="dashboard-servicios-pago"),
]
