from django.contrib import admin

from .models import (
    ConfiguracionEncomiendas, Envio, EventoTracking, PuntoEntregaDestino, RendicionCaja,
    RutaReparto, TarifaZona, ZonaReparto,
)

admin.site.register(ConfiguracionEncomiendas)


@admin.register(RendicionCaja)
class RendicionCajaAdmin(admin.ModelAdmin):
    list_display = ["codigo", "transportista", "esperado", "entregado", "diferencia", "estado", "creado_en"]
    list_filter = ["estado"]
    search_fields = ["codigo", "transportista__nombre"]


@admin.register(RutaReparto)
class RutaRepartoAdmin(admin.ModelAdmin):
    list_display = ["codigo", "fecha", "estado", "transportista", "iniciada_en", "cerrada_en"]
    list_filter = ["estado", "fecha"]
    search_fields = ["codigo", "transportista__nombre"]
    date_hierarchy = "fecha"


@admin.register(ZonaReparto)
class ZonaRepartoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "orden", "activo"]
    list_editable = ["orden", "activo"]


@admin.register(TarifaZona)
class TarifaZonaAdmin(admin.ModelAdmin):
    list_display = ["origen", "destino", "nivel", "precio_base", "incluye_kg", "precio_kg_extra", "eta_horas", "activo"]
    list_filter = ["nivel", "activo", "origen", "destino"]


@admin.register(PuntoEntregaDestino)
class PuntoEntregaDestinoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "ciudad", "telefono", "activo"]
    list_filter = ["activo", "ciudad"]
    search_fields = ["nombre", "ciudad"]
    list_editable = ["activo"]


class EventoInline(admin.TabularInline):
    model = EventoTracking
    extra = 0
    readonly_fields = ["estado", "descripcion", "ubicacion", "creado_por", "creado_en"]
    can_delete = False


@admin.register(Envio)
class EnvioAdmin(admin.ModelAdmin):
    list_display = ["codigo", "estado", "nivel", "origen_distrito", "destino_distrito",
                    "destinatario_nombre", "transportista", "precio", "creado_en"]
    list_filter = ["estado", "nivel", "es_contraentrega"]
    search_fields = ["codigo", "remitente_nombre", "destinatario_nombre",
                     "destinatario_telefono", "destino_direccion"]
    date_hierarchy = "creado_en"
    inlines = [EventoInline]
    raw_id_fields = ["transportista", "transportista_vehiculo", "creado_por"]
