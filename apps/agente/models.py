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


class ConversacionAgente(models.Model):
    """Un hilo de chat entre una persona y el agente (G1)."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="conversaciones_agente",
    )
    principal_tipo = models.CharField(max_length=16, db_index=True)
    titulo = models.CharField(max_length=120, blank=True)
    cerrada = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actualizado_en"]
        verbose_name = "Conversación con el agente"
        verbose_name_plural = "Conversaciones con el agente"

    def __str__(self):
        return f"#{self.pk} · {self.titulo or self.principal_tipo}"


class TurnoAgente(models.Model):
    ROL_USUARIO = "usuario"
    ROL_AGENTE = "agente"
    ROL_SISTEMA = "sistema"
    ROLES = [(ROL_USUARIO, "Usuario"), (ROL_AGENTE, "Agente"), (ROL_SISTEMA, "Sistema")]

    conversacion = models.ForeignKey(
        ConversacionAgente, on_delete=models.CASCADE, related_name="turnos",
    )
    rol = models.CharField(max_length=10, choices=ROLES)
    contenido = models.TextField(blank=True)
    tool_calls = models.JSONField(default=list, blank=True)
    iteraciones = models.PositiveSmallIntegerField(default=0)
    tokens_in = models.PositiveIntegerField(null=True, blank=True)
    tokens_out = models.PositiveIntegerField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado_en"]

    def __str__(self):
        return f"{self.conversacion_id}/{self.rol}: {self.contenido[:40]}"


class PropuestaAccion(models.Model):
    """Una acción crítica que el agente quiere hacer y espera confirmación humana."""

    ESTADO_PENDIENTE = "pendiente"
    ESTADO_APLICADA = "aplicada"
    ESTADO_RECHAZADA = "rechazada"
    ESTADO_VENCIDA = "vencida"
    ESTADOS = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_APLICADA, "Aplicada"),
        (ESTADO_RECHAZADA, "Rechazada"),
        (ESTADO_VENCIDA, "Vencida"),
    ]

    conversacion = models.ForeignKey(
        ConversacionAgente, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="propuestas",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="propuestas_agente", help_text="Quién la ve / la confirma.",
    )
    capacidad = models.CharField(max_length=64, db_index=True)
    efecto = models.CharField(max_length=24)
    args = models.JSONField(default=dict)
    resumen = models.TextField()
    estado = models.CharField(max_length=12, choices=ESTADOS, default=ESTADO_PENDIENTE, db_index=True)
    resuelta_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    resuelta_en = models.DateTimeField(null=True, blank=True)
    motivo_rechazo = models.CharField(max_length=200, blank=True)
    resultado = models.JSONField(default=dict, blank=True)
    accion_agente = models.ForeignKey(
        AccionAgente, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["usuario", "estado"])]
        verbose_name = "Propuesta del agente"
        verbose_name_plural = "Propuestas del agente"

    def __str__(self):
        return f"{self.capacidad} · {self.estado}"
