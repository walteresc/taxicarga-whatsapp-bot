from django.contrib import admin

from .models import EjemploConversacion


@admin.register(EjemploConversacion)
class EjemploConversacionAdmin(admin.ModelAdmin):
    list_display = (
        "referencia_chat",
        "turno",
        "etiquetas",
        "requiere_revision",
        "fecha_importacion",
    )
    list_filter = ("requiere_revision", "fuente", "fecha_importacion")
    search_fields = ("mensaje_cliente", "respuesta_negocio", "referencia_chat")
    readonly_fields = ("fecha_importacion",)
