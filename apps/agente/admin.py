from django.contrib import admin

from .models import (
    AccionAgente, ConversacionAgente, DocumentoConocimiento, PropuestaAccion, TurnoAgente,
)


@admin.register(DocumentoConocimiento)
class DocumentoConocimientoAdmin(admin.ModelAdmin):
    list_display = ["titulo", "categoria", "visibilidad", "activo", "actualizado_en"]
    list_filter = ["categoria", "visibilidad", "activo"]
    search_fields = ["titulo", "contenido"]
    prepopulated_fields = {"slug": ["titulo"]}

    def save_model(self, request, obj, form, change):
        obj.actualizado_por = request.user
        super().save_model(request, obj, form, change)


class TurnoInline(admin.TabularInline):
    model = TurnoAgente
    extra = 0
    fields = ["rol", "contenido", "tool_calls", "iteraciones", "tokens_in", "tokens_out", "creado_en"]
    readonly_fields = fields
    can_delete = False


@admin.register(ConversacionAgente)
class ConversacionAgenteAdmin(admin.ModelAdmin):
    list_display = ["id", "titulo", "principal_tipo", "usuario", "cerrada", "actualizado_en"]
    list_filter = ["principal_tipo", "cerrada"]
    search_fields = ["titulo", "usuario__username"]
    inlines = [TurnoInline]


@admin.register(PropuestaAccion)
class PropuestaAccionAdmin(admin.ModelAdmin):
    list_display = ["creado_en", "capacidad", "estado", "usuario", "resuelta_por", "resuelta_en"]
    list_filter = ["estado", "efecto", "capacidad"]
    search_fields = ["capacidad", "resumen", "usuario__username"]
    readonly_fields = [f.name for f in PropuestaAccion._meta.fields]


@admin.register(AccionAgente)
class AccionAgenteAdmin(admin.ModelAdmin):
    list_display = ["creado_en", "capacidad", "principal_tipo", "usuario", "ok", "codigo_error"]
    list_filter = ["ok", "efecto", "principal_tipo", "capacidad"]
    search_fields = ["capacidad", "usuario__username", "error", "lead__codigo", "servicio__codigo"]
    date_hierarchy = "creado_en"
    readonly_fields = [f.name for f in AccionAgente._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
