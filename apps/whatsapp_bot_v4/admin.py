from django.contrib import admin
from .models import BotGlobalConfig, ConversationOwnership, BotConversationState, WebhookEvent


@admin.register(BotGlobalConfig)
class BotGlobalConfigAdmin(admin.ModelAdmin):
    list_display = ('is_paused', 'paused_at', 'updated_at')
    fieldsets = (
        ('Estado', {
            'fields': ('is_paused', 'paused_at')
        }),
    )
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        # Solo una instancia puede existir
        return not BotGlobalConfig.objects.exists()


@admin.register(ConversationOwnership)
class ConversationOwnershipAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'owner_type', 'advisor_id', 'control_mode', 'updated_at')
    list_filter = ('owner_type', 'control_mode', 'updated_at')
    search_fields = ('conversation__cliente__telefono',)
    fieldsets = (
        ('Conversación', {
            'fields': ('conversation',)
        }),
        ('Control', {
            'fields': ('owner_type', 'control_mode', 'advisor_id')
        }),
        ('Timeout', {
            'fields': ('last_human_message_at', 'auto_return_to_bot_after_minutes')
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BotConversationState)
class BotConversationStateAdmin(admin.ModelAdmin):
    list_display = ('conversation_key', 'service_type', 'status', 'version', 'updated_at')
    list_filter = ('status', 'service_type', 'updated_at')
    search_fields = ('conversation_key',)
    fieldsets = (
        ('Conversación', {
            'fields': ('conversation_key', 'version')
        }),
        ('Estado', {
            'fields': ('service_type', 'status', 'state_data')
        }),
        ('Cotización', {
            'fields': ('quote_mode', 'quote_price', 'quote_input_hash')
        }),
        ('Reserva', {
            'fields': ('reservation_data', 'request_boundary_at')
        }),
    )
    readonly_fields = ('updated_at',)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('source', 'external_message_id', 'event_type', 'processed_at')
    list_filter = ('source', 'event_type', 'processed_at')
    search_fields = ('external_message_id',)
    fieldsets = (
        ('Webhook', {
            'fields': ('source', 'external_message_id', 'event_type')
        }),
        ('Timestamps', {
            'fields': ('processed_at',)
        }),
    )
    readonly_fields = ('processed_at',)
