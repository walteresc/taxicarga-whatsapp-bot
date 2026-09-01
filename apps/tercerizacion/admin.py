from django.contrib import admin

from .models import OfertaTransportista, PublicacionCarga, TransportistaBotState


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
    list_display = ["publicacion", "cliente", "precio_ofertado", "estado", "creado_en"]
    list_filter = ["estado"]
    search_fields = ["publicacion__codigo", "cliente__nombre", "cliente__telefono"]


@admin.register(TransportistaBotState)
class TransportistaBotStateAdmin(admin.ModelAdmin):
    list_display = ["conversacion", "paso", "publicacion_activa", "actualizado_en"]
    list_filter = ["paso"]
