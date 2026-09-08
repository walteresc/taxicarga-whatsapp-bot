from django.contrib import admin

from apps.planilla.models import ConfiguracionPlanilla


@admin.register(ConfiguracionPlanilla)
class ConfiguracionPlanillaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "tipo_contrato", "monto_dia", "monto_mes", "activo")
    list_filter = ("tipo", "tipo_contrato", "activo")
    search_fields = ("conductor__nombre", "ayudante__nombre", "usuario__username")
