from django.db import models


class BotConversationState(models.Model):
    STATUS_COLLECTING = "collecting"
    STATUS_READY = "ready_to_quote"
    STATUS_QUOTED = "quoted"
    STATUS_PENDING_HUMAN = "pending_human_quote"
    STATUSES = [
        (STATUS_COLLECTING, "Recolectando datos"),
        (STATUS_READY, "Lista para cotizar"),
        (STATUS_QUOTED, "Cotizada"),
        (STATUS_PENDING_HUMAN, "Pendiente de cotización humana"),
    ]

    conversation_key = models.CharField(max_length=160, unique=True)
    service_type = models.CharField(max_length=40, default="mudanza")
    state_data = models.JSONField(default=dict)
    status = models.CharField(max_length=24, choices=STATUSES, default=STATUS_COLLECTING)
    version = models.PositiveIntegerField(default=1)
    quote_input_hash = models.CharField(max_length=64, blank=True)
    quote_mode = models.CharField(max_length=16, blank=True)
    quote_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["conversation_key"]

    def __str__(self):
        return f"{self.conversation_key} v{self.version}"


class V4ChannelRoute(models.Model):
    channel = models.OneToOneField(
        "whatsapp.WhatsAppChannel",
        on_delete=models.CASCADE,
        related_name="v4_route",
    )
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"V4 channel {self.channel_id}: {'enabled' if self.enabled else 'disabled'}"
