from django.contrib import admin

from .models import AccionAgente


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
