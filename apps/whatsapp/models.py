from django.conf import settings
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


BOT = "bot"
HUMANO = "humano"
MIXTO = "mixto"

MODO_ATENCION_CHOICES = [
    (BOT, "Solo bot"),
    (HUMANO, "Solo humano"),
    (MIXTO, "Mixto"),
]

NONE = "none"
FORCE_BOT = "force_bot"
FORCE_HUMAN = "force_human"
FORCE_MIXTO = "force_mixto"

OVERRIDE_MODO_CHOICES = [
    (NONE, "Ninguno"),
    (FORCE_BOT, "Forzar bot"),
    (FORCE_HUMAN, "Forzar humano"),
    (FORCE_MIXTO, "Forzar mixto inteligente"),
]

DIAS_SEMANA = [
    ("lunes", "Lunes"),
    ("martes", "Martes"),
    ("miercoles", "Miércoles"),
    ("jueves", "Jueves"),
    ("viernes", "Viernes"),
    ("sabado", "Sábado"),
    ("domingo", "Domingo"),
]

DAY_CHOICES = [
    (0, "Lunes"),
    (1, "Martes"),
    (2, "Miércoles"),
    (3, "Jueves"),
    (4, "Viernes"),
    (5, "Sábado"),
    (6, "Domingo"),
]


class WhatsAppChannel(models.Model):
    nombre = models.CharField(max_length=100)
    phone_number_id = models.CharField(max_length=30, unique=True)
    numero_visible = models.CharField(max_length=20, blank=True, default="")
    asesor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="canales_whatsapp",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Canal WhatsApp"
        verbose_name_plural = "Canales WhatsApp"

    def __str__(self):
        return f"{self.nombre} - {self.numero_visible or self.phone_number_id}"


class ConfiguracionBot(models.Model):
    channel = models.ForeignKey(
        WhatsAppChannel,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="configuraciones_bot",
    )
    bot_activo = models.BooleanField(default=True)
    modo_atencion = models.CharField(
        max_length=10,
        choices=MODO_ATENCION_CHOICES,
        default=BOT,
    )
    hora_inicio_bot = models.TimeField(default="07:00")
    hora_fin_bot = models.TimeField(default="23:00")
    lunes_activo = models.BooleanField(default=True)
    martes_activo = models.BooleanField(default=True)
    miercoles_activo = models.BooleanField(default=True)
    jueves_activo = models.BooleanField(default=True)
    viernes_activo = models.BooleanField(default=True)
    sabado_activo = models.BooleanField(default=True)
    domingo_activo = models.BooleanField(default=False)
    mensaje_fuera_horario = models.TextField(
        blank=True,
        default="Gracias por contactarnos. Nuestro horario de atencion es de Lunes a Sabado de 7:00 a 23:00. Un asesor te atenderá en breve.",
    )
    override_activo = models.BooleanField(default=False)
    override_modo = models.CharField(
        max_length=12,
        choices=OVERRIDE_MODO_CHOICES,
        default=NONE,
    )
    override_desde = models.DateTimeField(null=True, blank=True)
    override_hasta = models.DateTimeField(null=True, blank=True)
    override_motivo = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración del bot"
        verbose_name_plural = "Configuración del bot"

    def __str__(self):
        estado = "activo" if self.bot_activo else "inactivo"
        canal = f" [{self.channel.nombre}]" if self.channel else ""
        return f"Bot {estado} - {self.get_modo_atencion_display()}{canal}"

    @classmethod
    def obtener(cls, channel=None):
        if channel:
            obj = cls.objects.filter(channel=channel).first()
            if not obj:
                obj = cls.objects.create(channel=channel)
            return obj
        return cls.objects.filter(channel__isnull=True).first() or cls.objects.create()


class BotSchedule(models.Model):
    channel = models.ForeignKey(
        WhatsAppChannel,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="horarios_bot",
    )
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Horario del bot"
        verbose_name_plural = "Horarios del bot"
        ordering = ["day_of_week", "start_time"]

    def __str__(self):
        dias = dict(DAY_CHOICES)
        dia = dias.get(self.day_of_week, str(self.day_of_week))
        canal = f" [{self.channel.nombre}]" if self.channel else ""
        return f"{dia} {self.start_time:%H:%M}-{self.end_time:%H:%M}{canal}"
        return f"{dia} {self.start_time:%H:%M}-{self.end_time:%H:%M}"
