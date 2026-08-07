from django.urls import path

from . import views

urlpatterns = [
    path("", views.campo_index, name="dashboard-campo"),
    # API — estado (legacy kanban)
    path("api/cambiar-estado/", views.api_cambiar_estado, name="api-cambiar-estado"),
    path("api/actualizar-duracion/", views.api_actualizar_duracion, name="api-actualizar-duracion"),
    # API — pizarra calendario
    path("pizarra/equipo/crear/", views.api_crear_equipo_pizarra, name="pizarra-equipo-crear"),
    path("pizarra/programacion/crear/", views.api_crear_programacion_pizarra, name="pizarra-programacion-crear"),
    path("pizarra/programacion/mover/", views.api_mover_programacion_pizarra, name="pizarra-programacion-mover"),
    path("pizarra/programacion/asignar/", views.api_asignar_servicio_pizarra, name="pizarra-programacion-asignar"),
    path("pizarra/buscar-clientes/", views.api_buscar_clientes, name="pizarra-buscar-clientes"),
    path("pizarra/equipo/eliminar/", views.api_eliminar_equipo_pizarra, name="pizarra-equipo-eliminar"),
    # Vehículos
    path("vehiculos/", views.vehiculo_list, name="dashboard-campo-vehiculos"),
    path("vehiculos/nuevo/", views.vehiculo_create, name="vehiculo_create"),
    path("vehiculos/<int:pk>/editar/", views.vehiculo_edit, name="vehiculo_edit"),
    path("vehiculos/<int:pk>/toggle/", views.vehiculo_toggle, name="vehiculo_toggle"),
    # Conductores
    path("conductores/", views.conductor_list, name="dashboard-campo-conductores"),
    path("conductores/nuevo/", views.conductor_create, name="conductor_create"),
    path("conductores/<int:pk>/", views.conductor_detail, name="conductor_detail"),
    path("conductores/<int:pk>/editar/", views.conductor_edit, name="conductor_edit"),
    path("conductores/<int:pk>/toggle/", views.conductor_toggle, name="conductor_toggle"),
    # Ayudantes
    path("ayudantes/", views.ayudante_list, name="dashboard-campo-ayudantes"),
    path("ayudantes/nuevo/", views.ayudante_create, name="ayudante_create"),
    path("ayudantes/<int:pk>/", views.ayudante_detail, name="ayudante_detail"),
    path("ayudantes/<int:pk>/editar/", views.ayudante_edit, name="ayudante_edit"),
    path("ayudantes/<int:pk>/toggle/", views.ayudante_toggle, name="ayudante_toggle"),
    # Equipos frecuentes
    path("equipos-frecuentes/", views.equipos_frecuentes_list, name="dashboard-campo-equipos-frecuentes"),
    path("equipos-frecuentes/crear-ajax/", views.equipos_frecuentes_crear_ajax, name="ef-crear-ajax"),
    path("equipos-frecuentes/<int:pk>/editar-ajax/", views.equipos_frecuentes_editar_ajax, name="ef-editar-ajax"),
    path("equipos-frecuentes/<int:pk>/eliminar-ajax/", views.equipos_frecuentes_eliminar_ajax, name="ef-eliminar-ajax"),
    path("pizarra/equipo/desde-frecuente/", views.api_crear_equipo_desde_frecuente, name="pizarra-equipo-desde-frecuente"),
    # Equipos
    path("equipos/", views.equipo_calendario, name="dashboard-campo-equipos"),
    path("equipos/validar/", views.equipo_validar_ajax, name="equipo-validar-ajax"),
    path("equipos/crear-ajax/", views.equipo_crear_ajax, name="equipo-crear-ajax"),
    path("equipos/<int:pk>/editar-ajax/", views.equipo_editar_ajax, name="equipo-editar-ajax"),
    path("equipos/nuevo/", views.equipo_create, name="equipo_create"),
    path("equipos/<int:pk>/", views.equipo_detail, name="equipo_detail"),
    path("equipos/<int:pk>/editar/", views.equipo_edit, name="equipo_edit"),
    path("equipos/<int:pk>/toggle/", views.equipo_toggle, name="equipo_toggle"),
    path("equipos/<int:pk>/eliminar-ajax/", views.equipo_eliminar_ajax, name="equipo-eliminar-ajax"),
]
