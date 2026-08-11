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
