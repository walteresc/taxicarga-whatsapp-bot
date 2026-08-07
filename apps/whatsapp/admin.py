from django.contrib import admin

from .models import (
    AuditoriaWhatsApp,
    BotSchedule,
    ConfiguracionBot,
    ConversacionWhatsApp,
    EvidenciaWhatsapp,
    MensajeWhatsApp,
    MensajeWhatsappProcesado,
    WhatsAppChannel,
)


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


@admin.register(WhatsAppChannel)
class WhatsAppChannelAdmin(admin.ModelAdmin):
    list_display = ("nombre", "numero_visible", "asesor", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "numero_visible", "phone_number_id")


@admin.register(ConfiguracionBot)
class ConfiguracionBotAdmin(admin.ModelAdmin):
    list_display = ("channel", "bot_activo", "modo_atencion", "updated_at")
    list_filter = ("bot_activo", "modo_atencion")


@admin.register(BotSchedule)
class BotScheduleAdmin(admin.ModelAdmin):
    list_display = ("channel", "day_of_week", "start_time", "end_time", "is_active")
    list_filter = ("day_of_week", "is_active")


@admin.register(ConversacionWhatsApp)
class ConversacionWhatsAppAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "cliente",
        "channel",
        "estado_atencion",
        "estado_recopilacion",
        "estado_cotizacion",
        "responsable",
        "ultima_actividad",
    )
    list_filter = ("estado_atencion", "estado_recopilacion", "estado_cotizacion", "channel")
    search_fields = ("cliente__nombre", "cliente__telefono", "resumen", "motivo_derivacion")
    readonly_fields = ("creada_en", "actualizada_en")


@admin.register(MensajeWhatsApp)
class MensajeWhatsAppAdmin(admin.ModelAdmin):
    list_display = ("id", "conversacion", "origen", "tipo", "estado", "fecha_mensaje")
    list_filter = ("origen", "tipo", "estado")
    search_fields = ("meta_message_id", "contenido")
    readonly_fields = [field.name for field in MensajeWhatsApp._meta.fields]


@admin.register(AuditoriaWhatsApp)
class AuditoriaWhatsAppAdmin(admin.ModelAdmin):
    list_display = ("evento", "conversacion", "actor", "creado_en")
    list_filter = ("evento", "creado_en")
    search_fields = ("evento", "conversacion__cliente__nombre")
    readonly_fields = [field.name for field in AuditoriaWhatsApp._meta.fields]
