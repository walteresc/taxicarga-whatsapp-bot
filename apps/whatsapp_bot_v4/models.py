from django.db import models
from django.contrib.auth.models import User


class BotConversationState(models.Model):
    STATUS_COLLECTING = "collecting"
    STATUS_READY = "ready_to_quote"
    STATUS_QUOTED = "quoted"
    STATUS_PENDING_HUMAN = "pending_human_quote"
    STATUS_RESERVATION = "reservation"
    STATUSES = [
        (STATUS_COLLECTING, "Recolectando datos"),
        (STATUS_READY, "Lista para cotizar"),
        (STATUS_QUOTED, "Cotizada"),
        (STATUS_PENDING_HUMAN, "Pendiente de cotización humana"),
        (STATUS_RESERVATION, "Reservando servicio"),
    ]

    conversation_key = models.CharField(max_length=160, unique=True)
    service_type = models.CharField(max_length=40, default="mudanza")
    state_data = models.JSONField(default=dict)
    status = models.CharField(max_length=24, choices=STATUSES, default=STATUS_COLLECTING)
    version = models.PositiveIntegerField(default=1)
    quote_input_hash = models.CharField(max_length=64, blank=True)
    quote_mode = models.CharField(max_length=16, blank=True)
    quote_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    request_boundary_at = models.DateTimeField(null=True, blank=True)
    reservation_data = models.JSONField(default=dict)
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


class ConversationOwnership(models.Model):
    """Control de conversación agnóstico a CRM/Chatwoot.

    Define quién controla la conversación: bot, asesor, o ambos.
    Soporta modo manual (CRM decide) o automático (timeout).
    """

    OWNER_BOT = "bot"
    OWNER_ADVISOR = "advisor"
    OWNER_HYBRID = "hybrid"
    OWNER_CHOICES = [
        (OWNER_BOT, "Bot"),
        (OWNER_ADVISOR, "Advisor"),
        (OWNER_HYBRID, "Both (advisor priority)"),
    ]

    MODE_MANUAL = "manual"
    MODE_AUTOMATIC = "automatic"
    MODE_CHOICES = [
        (MODE_MANUAL, "Manual via CRM buttons"),
        (MODE_AUTOMATIC, "Auto-detect advisor activity"),
    ]

    conversation = models.OneToOneField(
        "whatsapp.ConversacionWhatsApp",
        on_delete=models.CASCADE,
        related_name="ownership"
    )
    owner_type = models.CharField(max_length=10, choices=OWNER_CHOICES, default=OWNER_BOT)
    advisor_id = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    control_mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_MANUAL)
    last_human_message_at = models.DateTimeField(null=True, blank=True)
    auto_return_to_bot_after_minutes = models.IntegerField(default=15)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("conversation",)

    def __str__(self):
        return f"Conv {self.conversation.pk}: {self.owner_type} ({self.control_mode})"

    def is_bot_allowed(self):
        """Determina si el bot puede responder ahora."""
        if self.owner_type == self.OWNER_BOT:
            return True

        # Asesor tiene control - NO responde bot
        if self.owner_type == self.OWNER_ADVISOR:
            # Modo automático: chequear timeout
            if self.control_mode == self.MODE_AUTOMATIC:
                if not self.last_human_message_at:
                    return False
                from django.utils import timezone
                from datetime import timedelta
                elapsed = timezone.now() - self.last_human_message_at
                if elapsed > timedelta(minutes=self.auto_return_to_bot_after_minutes):
                    # Pasó timeout - devolver control a bot
                    self.owner_type = self.OWNER_BOT
                    self.save(update_fields=["owner_type"])
                    return True
            # Modo manual o timeout no pasó: bot NO responde
            return False

        return True


class BotGlobalConfig(models.Model):
    """Control global del bot (pausar/activar en todas conversaciones)"""
    is_paused = models.BooleanField(default=False)
    paused_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Bot Global Config"

    def __str__(self):
        return f"Bot {'paused' if self.is_paused else 'active'}"


class WebhookEvent(models.Model):
    """Tabla de idempotencia para webhooks (Meta y YCloud)"""
    SOURCE_CHOICES = [
        ('meta', 'Meta Graph API'),
        ('ycloud', 'YCloud'),
    ]

    source = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    external_message_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('source', 'external_message_id')
        ordering = ['-processed_at']
        verbose_name = 'Webhook Event'
        verbose_name_plural = 'Webhook Events'

    def __str__(self):
        return f"{self.source}: {self.event_type} ({self.external_message_id})"
