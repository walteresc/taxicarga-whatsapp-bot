from django.contrib import admin

from .models import Cotizacion, ServicioHistorico


@admin.register(ServicioHistorico)
class ServicioHistoricoAdmin(admin.ModelAdmin):
    list_display = (
        "fecha",
        "tipo_servicio",
        "distrito_origen",
        "distrito_destino",
        "precio_cotizado",
        "precio_final",
        "cerrado",
    )
    list_filter = ("tipo_servicio", "modalidad_servicio", "cerrado", "fecha")
    search_fields = (
        "distrito_origen",
        "distrito_destino",
        "lista_objetos",
        "objetos_pesados",
        "camion_usado",
        "observaciones",
    )


@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = (
        "lead",
        "precio_min",
        "precio_max",
        "precio_recomendado",
        "servicios_similares_encontrados",
        "fecha_creacion",
    )
    readonly_fields = ("fecha_creacion",)

# Register your models here.
