from django.contrib import admin

from .models import MantenimientoVehiculo


@admin.register(MantenimientoVehiculo)
class MantenimientoVehiculoAdmin(admin.ModelAdmin):
    list_display = ["vehiculo", "fecha_mantenimiento", "kilometraje_actual", "proximo_mantenimiento_km"]
    list_filter = ["fecha_mantenimiento", "vehiculo"]
    search_fields = ["vehiculo__placa", "descripcion"]
