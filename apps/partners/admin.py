from django.contrib import admin

from .models import ApiKey, IdempotencyRecord, SocioComercial, WebhookDelivery


class ApiKeyInline(admin.TabularInline):
    model = ApiKey
    extra = 0
    fields = ["entorno", "prefix", "activa", "ultimo_uso_en", "creado_en"]
    readonly_fields = ["prefix", "ultimo_uso_en", "creado_en"]


@admin.register(SocioComercial)
class SocioComercialAdmin(admin.ModelAdmin):
    list_display = ["nombre", "activo", "saldo", "webhook_url", "creado_en"]
    list_filter = ["activo"]
    search_fields = ["nombre", "contacto_email"]
    inlines = [ApiKeyInline]


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ["socio", "evento", "estado", "intentos", "ultimo_codigo", "creado_en"]
    list_filter = ["estado", "evento"]
    search_fields = ["socio__nombre"]
    readonly_fields = [f.name for f in WebhookDelivery._meta.fields]

    def has_add_permission(self, request):
        return False


admin.site.register(IdempotencyRecord)
