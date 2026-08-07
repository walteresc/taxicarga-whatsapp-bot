from django.contrib import admin

from .models import (
    Cotizacion,
    CotizacionComercial,
    EnvioCotizacion,
    RevisionCotizacion,
    ServicioHistorico,
    SolicitudCotizacion,
)


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


@admin.register(SolicitudCotizacion)
class SolicitudCotizacionAdmin(admin.ModelAdmin):
    list_display = ("id", "lead", "estado", "prioridad", "asignada_a", "creada_en")
    list_filter = ("estado", "prioridad")
    search_fields = ("lead__cliente__nombre", "lead__cliente__telefono", "motivo")


class RevisionCotizacionInline(admin.TabularInline):
    model = RevisionCotizacion
    extra = 0
    readonly_fields = ("numero", "precio_final", "enviada", "creada_en", "enviada_en")


@admin.register(CotizacionComercial)
class CotizacionComercialAdmin(admin.ModelAdmin):
    list_display = ("codigo", "lead", "origen", "estado", "asesor", "creada_en")
    list_filter = ("origen", "estado", "channel")
    search_fields = ("codigo", "lead__cliente__nombre", "lead__cliente__telefono")
    inlines = (RevisionCotizacionInline,)


@admin.register(EnvioCotizacion)
class EnvioCotizacionAdmin(admin.ModelAdmin):
    list_display = ("revision", "channel", "estado", "intento", "creado_en")
    list_filter = ("estado", "channel")
    search_fields = ("meta_message_id", "revision__cotizacion__codigo")
    readonly_fields = ("creado_en", "actualizado_en", "entregado_en")

# Register your models here.
