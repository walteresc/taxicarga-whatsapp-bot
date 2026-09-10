from django.contrib import admin

from .models import OrdenPago


@admin.register(OrdenPago)
class OrdenPagoAdmin(admin.ModelAdmin):
    list_display = [
        "servicio", "concepto", "monto", "pasarela", "estado",
        "external_id", "origen", "creado_en", "pagado_en",
    ]
    list_filter = ["estado", "pasarela", "origen", "concepto"]
    search_fields = ["servicio__codigo", "external_id", "token", "email_pagador"]
    date_hierarchy = "creado_en"
    readonly_fields = [f.name for f in OrdenPago._meta.fields]

    def has_add_permission(self, request):
        return False
