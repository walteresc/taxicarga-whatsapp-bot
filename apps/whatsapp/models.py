from django.db import models

from apps.clientes.models import Cliente
from apps.leads.models import Lead


class EvidenciaWhatsapp(models.Model):
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="evidencias_whatsapp",
    )
    lead = models.ForeignKey(
        Lead,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidencias_whatsapp",
    )
    media_id = models.CharField(max_length=160, unique=True)
    archivo = models.FileField(upload_to="whatsapp/%Y/%m/")
    mime_type = models.CharField(max_length=100)
    sha256_meta = models.CharField(max_length=128, blank=True)
    caption = models.TextField(blank=True)
    analisis_visual = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Foto WhatsApp {self.cliente_id} - {self.fecha:%Y-%m-%d %H:%M}"


class MensajeWhatsappProcesado(models.Model):
    message_id = models.CharField(max_length=255, unique=True)
    telefono = models.CharField(max_length=30, blank=True)
    tipo = models.CharField(max_length=30, blank=True)
    completado = models.BooleanField(default=False)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return self.message_id

# Create your models here.
