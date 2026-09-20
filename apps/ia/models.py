from django.db import models


class EjemploConversacion(models.Model):
    fuente = models.CharField(max_length=40, default="whatsapp_export")
    referencia_chat = models.CharField(max_length=80)
    turno = models.PositiveIntegerField()
    mensaje_cliente = models.TextField()
    respuesta_negocio = models.TextField()
    etiquetas = models.JSONField(default=list, blank=True)
    requiere_revision = models.BooleanField(default=False)
    fecha_importacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["referencia_chat", "turno"]
        constraints = [
            models.UniqueConstraint(
                fields=["fuente", "referencia_chat", "turno"],
                name="ejemplo_conversacion_fuente_chat_turno_unico",
            )
        ]

    def __str__(self):
        return f"{self.referencia_chat} - turno {self.turno}"


class AIDeltaAudit(models.Model):
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_FALLBACK = "fallback"
    STATUS_CHOICES = (
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_FALLBACK, "Fallback"),
    )

    conversation_id = models.PositiveBigIntegerField(db_index=True)
    message_id = models.PositiveBigIntegerField(unique=True)
    lead = models.ForeignKey(
        "leads.Lead", on_delete=models.CASCADE, related_name="ai_delta_audits"
    )
    provider = models.CharField(max_length=30, blank=True)
    model = models.CharField(max_length=80, blank=True)
    schema_version = models.PositiveSmallIntegerField(default=1)
    state_version = models.CharField(max_length=64)
    mode = models.CharField(max_length=20, default="shadow")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    accepted_delta = models.JSONField(default=dict, blank=True)
    raw_delta = models.JSONField(default=dict, blank=True)
    rejected_delta = models.JSONField(default=list, blank=True)
    question_targets = models.JSONField(default=list, blank=True)
    canonical_state_before = models.JSONField(default=dict, blank=True)
    canonical_state_after = models.JSONField(default=dict, blank=True)
    legacy_extraction = models.JSONField(default=dict, blank=True)
    rejected_fields = models.JSONField(default=list, blank=True)
    rejection_reasons = models.JSONField(default=list, blank=True)
    fallback_used = models.BooleanField(default=False)
    error_type = models.CharField(max_length=100, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    latency_ms = models.FloatField(null=True, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"], name="ia_delta_status_idx")
        ]


class ConfiguracionIA(models.Model):
    """Qué proveedor/modelo de IA usar por propósito (singleton) — permite
    cambiarlo desde el panel de Configuración sin redeploy. La API key NUNCA
    vive acá: sigue siendo exclusivamente de `.env`/infraestructura (decisión
    de seguridad — ver `apps/ia/providers.py`); esto solo elige CUÁL usar.

    Todo vacío por defecto = "usar lo que diga el .env del servidor"
    (`settings.AI_PROVIDER`/`AI_EXTRACTION_PROVIDER`/etc., comportamiento
    actual sin cambios) — un despliegue nuevo sin tocar esta pantalla se
    comporta exactamente igual que antes de que existiera este modelo."""

    PROVEEDOR_CHOICES = [("openai", "OpenAI"), ("deepseek", "DeepSeek")]
    PROVEEDOR_O_DEFAULT = [("", "Usar el valor del servidor (.env)"), *PROVEEDOR_CHOICES]

    proveedor_default = models.CharField(
        max_length=10, choices=PROVEEDOR_O_DEFAULT, blank=True, default="",
        help_text="Proveedor general — aplica a extracción/conversación/copiloto salvo que se anule abajo.",
    )
    proveedor_extraccion = models.CharField(max_length=10, choices=PROVEEDOR_O_DEFAULT, blank=True, default="")
    proveedor_conversacion = models.CharField(max_length=10, choices=PROVEEDOR_O_DEFAULT, blank=True, default="")
    proveedor_copiloto = models.CharField(max_length=10, choices=PROVEEDOR_O_DEFAULT, blank=True, default="")

    modelo_openai = models.CharField(
        max_length=60, blank=True, default="",
        help_text="Vacío = usa el modelo por defecto del servidor (OPENAI_MODEL).",
    )
    modelo_deepseek = models.CharField(
        max_length=60, blank=True, default="",
        help_text="Vacío = usa el modelo por defecto del servidor (DEEPSEEK_MODEL).",
    )

    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de IA"
        verbose_name_plural = "Configuración de IA"

    def __str__(self):
        return f"Configuración de IA (proveedor default: {self.proveedor_default or 'servidor'})"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
