from django.db import models
from django.utils import timezone


class Cliente(models.Model):
    nombre = models.CharField(max_length=160, blank=True)
    telefono = models.CharField(max_length=30, unique=True)
    documento = models.CharField(max_length=20, blank=True, default="")
    correo = models.EmailField(max_length=200, blank=True, default="")
    ruc = models.CharField(max_length=20, blank=True, default="")
    razon_social = models.CharField(max_length=200, blank=True, default="")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    ultima_interaccion = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-ultima_interaccion"]

    def __str__(self):
        return self.nombre or self.telefono


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
