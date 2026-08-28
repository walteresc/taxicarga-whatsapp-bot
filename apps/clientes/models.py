from django.db import models
from django.utils import timezone
from apps.clientes.phone_normalizer import normalize_phone


class Cliente(models.Model):
    SOURCE_MANUAL = "manual"
    SOURCE_CRM = "crm"
    SOURCE_CHANNEL = "channel"
    SOURCE_IMPORT = "import"
    SOURCE_FALLBACK = "fallback"

    NAME_SOURCES = [
        (SOURCE_MANUAL, "Manual (CRM)"),
        (SOURCE_CRM, "CRM/Lead"),
        (SOURCE_CHANNEL, "WhatsApp Channel"),
        (SOURCE_IMPORT, "Import"),
        (SOURCE_FALLBACK, "Fallback (phone)"),
    ]

    nombre = models.CharField(max_length=160, blank=True)
    telefono = models.CharField(max_length=30, unique=True)
    documento = models.CharField(max_length=20, blank=True, default="")
    correo = models.EmailField(max_length=200, blank=True, default="")
    ruc = models.CharField(max_length=20, blank=True, default="")
    razon_social = models.CharField(max_length=200, blank=True, default="")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    ultima_interaccion = models.DateTimeField(default=timezone.now)

    phone_e164 = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        db_index=True,
        help_text="Normalized phone in E.164 format (+51995403320)"
    )
    display_name = models.CharField(
        max_length=160,
        blank=True,
        help_text="Name displayed in CRM (manual or best-match)"
    )
    channel_profile_name = models.CharField(
        max_length=160,
        blank=True,
        help_text="Name from WhatsApp profile"
    )
    name_source = models.CharField(
        max_length=20,
        choices=NAME_SOURCES,
        default=SOURCE_FALLBACK,
        help_text="Source of display_name"
    )
    aliases = models.JSONField(
        default=list,
        blank=True,
        help_text="List of historical names: ['TEST Stage 7', 'ELI ESCOBAR', ...]"
    )
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="merged_from",
        help_text="If not null, this cliente has been merged into another"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Deactivated if merged or duplicate"
    )
    ycloud_user_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="YCloud internal fromUserId — fallback identity when the webhook omits 'from' (e.g. reply/quote messages)"
    )

    class Meta:
        ordering = ["-ultima_interaccion"]
        indexes = [
            models.Index(fields=["phone_e164"]),
            models.Index(fields=["is_active", "-ultima_interaccion"]),
        ]

    def save(self, *args, **kwargs):
        # Normalize phone to E.164 format AND update telefono field
        if self.telefono:
            result = normalize_phone(self.telefono)
            if result["is_valid"]:
                # Store both the E.164 version and update original field for consistency
                self.phone_e164 = result["normalized_e164"]
                # IMPORTANT: Also update telefono to E.164 so phone_identity queries work consistently
                self.telefono = result["normalized_e164"]

        # Set display_name if not set
        if not self.display_name:
            self.display_name = self.nombre or ""

        super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name or self.nombre or self.telefono


class Conversacion(models.Model):
    CANAL_WHATSAPP = "whatsapp"
    CANALES = [(CANAL_WHATSAPP, "WhatsApp")]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="conversaciones",
    )
    mensaje_entrada = models.TextField(blank=True)
    mensaje_salida = models.TextField(blank=True)
    canal = models.CharField(max_length=30, choices=CANALES, default=CANAL_WHATSAPP)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.cliente} - {self.fecha:%Y-%m-%d %H:%M}"

# Create your models here.
