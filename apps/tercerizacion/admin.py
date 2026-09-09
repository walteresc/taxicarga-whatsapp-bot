from django.contrib import admin

from .models import (
    HiloNegociacion, MensajeNegociacion, OfertaTransportista, PublicacionCarga,
    TransportistaBotState,
)


class OfertaTransportistaInline(admin.TabularInline):
    model = OfertaTransportista
    extra = 0
    fields = ["cliente", "precio_ofertado", "estado", "creado_en"]
    readonly_fields = ["creado_en"]


@admin.register(PublicacionCarga)
class PublicacionCargaAdmin(admin.ModelAdmin):
    list_display = ["codigo", "servicio", "estado", "creado_por", "creado_en"]
    list_filter = ["estado"]
    search_fields = ["codigo", "servicio__codigo"]
    inlines = [OfertaTransportistaInline]


@admin.register(OfertaTransportista)
class OfertaTransportistaAdmin(admin.ModelAdmin):
    list_display = ["publicacion", "transportista", "cliente", "precio_ofertado", "monto_actual", "estado", "creado_en"]
    list_filter = ["estado"]
    search_fields = ["publicacion__codigo", "transportista__nombre", "cliente__nombre", "cliente__telefono"]


@admin.register(TransportistaBotState)
class TransportistaBotStateAdmin(admin.ModelAdmin):
    list_display = ["conversacion", "paso", "publicacion_activa", "actualizado_en"]
    list_filter = ["paso"]


class MensajeNegociacionInline(admin.TabularInline):
    model = MensajeNegociacion
    extra = 0
    fields = ["emisor", "canal", "tipo", "texto", "propuesta_monto", "propuesta_estado", "creado_en"]
    readonly_fields = ["creado_en"]


@admin.register(HiloNegociacion)
class HiloNegociacionAdmin(admin.ModelAdmin):
    list_display = ["id", "lead", "tipo", "estado", "contraparte", "monto_actual", "monto_acordado", "actualizado_en"]
    list_filter = ["tipo", "estado"]
    search_fields = ["lead__codigo", "contraparte__nombre", "publicacion__codigo"]
    inlines = [MensajeNegociacionInline]


@admin.register(MensajeNegociacion)
class MensajeNegociacionAdmin(admin.ModelAdmin):
    list_display = ["id", "hilo", "emisor", "tipo", "canal", "propuesta_monto", "propuesta_estado", "creado_en"]
    list_filter = ["emisor", "tipo", "canal", "propuesta_estado"]
    search_fields = ["hilo__lead__codigo", "texto"]
