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
