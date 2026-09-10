from django.contrib import admin

from .models import CuotaServicio, PagoReserva, Servicio


class CuotaServicioInline(admin.TabularInline):
    model = CuotaServicio
    extra = 0
    fields = ["orden", "disparador", "dias", "fecha_vencimiento", "base", "valor", "monto"]


@admin.register(CuotaServicio)
class CuotaServicioAdmin(admin.ModelAdmin):
    list_display = ["servicio", "orden", "disparador", "monto", "estado"]
    list_filter = ["disparador", "base"]
    search_fields = ["servicio__codigo"]


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    inlines = [CuotaServicioInline]
    list_display = [
        "codigo", "cliente", "estado", "tipo_servicio",
        "direccion_origen", "direccion_destino",
        "fecha_servicio", "precio", "asesor", "fecha_creacion",
    ]
    list_filter = ["estado", "fecha_servicio", "tipo_embalaje"]
    search_fields = ["codigo", "cliente__nombre", "cliente__telefono"]


@admin.register(PagoReserva)
class PagoReservaAdmin(admin.ModelAdmin):
    list_display = ["servicio", "concepto", "metodo_pago", "monto", "cuota", "fecha_pago", "usuario_registro"]
    list_filter = ["concepto", "metodo_pago"]
    search_fields = ["servicio__codigo"]
    raw_id_fields = ["servicio", "cuota"]
