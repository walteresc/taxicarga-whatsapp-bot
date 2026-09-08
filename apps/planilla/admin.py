from django.contrib import admin

from apps.planilla.models import (
    ConfiguracionPlanilla, MovimientoCompensacion, Pago, RegistroAsistencia, SaldoHorasMes,
)


@admin.register(ConfiguracionPlanilla)
class ConfiguracionPlanillaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "tipo_contrato", "monto_dia", "monto_mes", "activo")
    list_filter = ("tipo", "tipo_contrato", "activo")
    search_fields = ("conductor__nombre", "ayudante__nombre", "usuario__username")


@admin.register(RegistroAsistencia)
class RegistroAsistenciaAdmin(admin.ModelAdmin):
    list_display = ("trabajador", "fecha", "tipo_dia", "hora_ingreso", "hora_salida", "delta_dia")
    list_filter = ("tipo_dia",)
    date_hierarchy = "fecha"


@admin.register(SaldoHorasMes)
class SaldoHorasMesAdmin(admin.ModelAdmin):
    list_display = ("trabajador", "anio", "mes", "saldo_apertura", "editado_manual")


@admin.register(MovimientoCompensacion)
class MovimientoCompensacionAdmin(admin.ModelAdmin):
    list_display = ("trabajador", "fecha", "tipo", "horas")
    list_filter = ("tipo",)
    date_hierarchy = "fecha"


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("trabajador", "tipo", "periodo_hasta", "monto_neto", "pagado", "fecha_pago")
    list_filter = ("tipo", "pagado")
    date_hierarchy = "periodo_hasta"
