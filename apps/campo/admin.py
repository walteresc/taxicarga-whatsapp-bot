from django.contrib import admin

from .models import Ayudante, Conductor, EquipoDia, EquipoFrecuente, ProgramacionServicio, Vehiculo


@admin.register(Vehiculo)
class VehiculoAdmin(admin.ModelAdmin):
    list_display = ["placa", "marca", "modelo", "anio", "capacidad_toneladas", "activo"]
    list_filter = ["activo", "marca"]
    search_fields = ["placa", "marca", "modelo"]


@admin.register(Conductor)
class ConductorAdmin(admin.ModelAdmin):
    list_display = ["nombre", "dni", "telefono", "numero_licencia", "categoria_licencia", "activo"]
    list_filter = ["activo", "categoria_licencia"]
    search_fields = ["nombre", "dni", "telefono", "numero_licencia"]


@admin.register(Ayudante)
class AyudanteAdmin(admin.ModelAdmin):
    list_display = ["nombre", "dni", "telefono", "activo"]
    list_filter = ["activo"]
    search_fields = ["nombre", "dni", "telefono"]


@admin.register(EquipoDia)
class EquipoDiaAdmin(admin.ModelAdmin):
    list_display = ["fecha", "vehiculo", "conductor", "activo"]
    list_filter = ["activo", "fecha"]
    search_fields = ["vehiculo__placa", "conductor__nombre"]
    filter_horizontal = ["ayudantes"]


@admin.register(EquipoFrecuente)
class EquipoFrecuenteAdmin(admin.ModelAdmin):
    list_display = ["nombre", "vehiculo", "conductor", "activo", "orden"]
    list_filter = ["activo"]
    search_fields = ["nombre", "vehiculo__placa", "conductor__nombre"]
    filter_horizontal = ["ayudantes", "conductores_ayudantes"]
    ordering = ["orden", "nombre"]


@admin.register(ProgramacionServicio)
class ProgramacionServicioAdmin(admin.ModelAdmin):
    list_display = ["servicio", "fecha", "hora_inicio", "vehiculo", "conductor", "estado_operativo"]
    list_filter = ["estado_operativo", "fecha"]
    search_fields = ["servicio__codigo", "vehiculo__placa", "conductor__nombre"]
    filter_horizontal = ["ayudantes"]
