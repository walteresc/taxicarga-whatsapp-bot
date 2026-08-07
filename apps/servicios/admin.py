from django.contrib import admin

from .models import PagoReserva, Servicio


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = [
        "codigo", "cliente", "estado", "tipo_servicio",
        "direccion_origen", "direccion_destino",
        "fecha_servicio", "precio", "asesor", "fecha_creacion",
    ]
    list_filter = ["estado", "fecha_servicio", "tipo_embalaje"]
    search_fields = ["codigo", "cliente__nombre", "cliente__telefono"]


@admin.register(PagoReserva)
class PagoReservaAdmin(admin.ModelAdmin):
    list_display = ["servicio", "concepto", "metodo_pago", "monto", "fecha_pago", "usuario_registro"]
    list_filter = ["concepto", "metodo_pago"]
    search_fields = ["servicio__codigo"]
