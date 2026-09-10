from django.conf import settings
from django.db import models


class AccionAgente(models.Model):
    """Una llamada a una capacidad del agente. Se escribe SIEMPRE (éxito o error),
    desde `registro.ejecutar`. Es la traza de qué hizo (o intentó hacer) el
    agente, quién lo pidió y con qué resultado. Tabla aparte de
    `whatsapp.AuditoriaWhatsApp` (esa está acoplada al canal WhatsApp)."""

    principal_tipo = models.CharField(max_length=16, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    capacidad = models.CharField(max_length=64, db_index=True)
    efecto = models.CharField(max_length=24)
    args = models.JSONField(default=dict, blank=True)
    ok = models.BooleanField()
    codigo_error = models.CharField(max_length=32, blank=True)
    error = models.TextField(blank=True)
    resultado = models.JSONField(default=dict, blank=True)

    lead = models.ForeignKey(
        "leads.Lead", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    servicio = models.ForeignKey(
        "servicios.Servicio", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Acción del agente"
        verbose_name_plural = "Acciones del agente"
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["capacidad", "-creado_en"]),
            models.Index(fields=["ok", "-creado_en"]),
        ]

    def __str__(self):
        estado = "ok" if self.ok else (self.codigo_error or "error")
        return f"{self.capacidad} · {self.principal_tipo} · {estado}"
