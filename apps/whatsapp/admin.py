from django.contrib import admin

from .models import EvidenciaWhatsapp, MensajeWhatsappProcesado


@admin.register(EvidenciaWhatsapp)
class EvidenciaWhatsappAdmin(admin.ModelAdmin):
    list_display = ("cliente", "lead", "mime_type", "fecha")
    list_filter = ("mime_type", "fecha")
    search_fields = ("cliente__telefono", "cliente__nombre", "caption", "media_id")
    readonly_fields = (
        "cliente",
        "lead",
        "media_id",
        "archivo",
        "mime_type",
        "sha256_meta",
        "caption",
        "fecha",
    )


@admin.register(MensajeWhatsappProcesado)
class MensajeWhatsappProcesadoAdmin(admin.ModelAdmin):
    list_display = ("message_id", "tipo", "completado", "fecha")
    list_filter = ("tipo", "completado", "fecha")
    search_fields = ("message_id",)
    readonly_fields = ("message_id", "telefono", "tipo", "completado", "fecha")
