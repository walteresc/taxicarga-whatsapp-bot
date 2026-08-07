from django.conf import settings
from django.db import models
from django.utils import timezone

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

SOLO_ASESOR = "asesor"
RECOPILAR_DATOS = "recopilar"
COTIZACION_AUTOMATICA = "automatica"
HIBRIDO = "hibrido"

MODOS_OPERACION = [
    (SOLO_ASESOR, "Solo asesor"),
    (RECOPILAR_DATOS, "Recopilar datos"),
    (COTIZACION_AUTOMATICA, "Cotización automática"),
    (HIBRIDO, "Híbrido"),
]

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
    modo_operacion = models.CharField(
        max_length=20,
        choices=MODOS_OPERACION,
        default=COTIZACION_AUTOMATICA,
    )
    zona_horaria = models.CharField(max_length=64, default="America/Lima")
    transferir_fuera_horario = models.BooleanField(default=True)
    confianza_minima = models.DecimalField(max_digits=5, decimal_places=2, default=85)
    margen_minimo_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    espera_asesor_minutos = models.PositiveSmallIntegerField(default=15)
    seguimiento_horas = models.PositiveSmallIntegerField(default=24)
    asesor_predeterminado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configuraciones_bot_predeterminadas",
    )
    reglas_automaticas = models.JSONField(default=list, blank=True)
    mensaje_bienvenida = models.TextField(blank=True, default="")
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
    MODO_CHOICES = [
        ('bot', 'Bot automático'),
        ('mixto', 'Bot mixto inteligente'),
    ]

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
    modo = models.CharField(
        max_length=20,
        choices=MODO_CHOICES,
        default='bot',
    )

    class Meta:
        verbose_name = "Horario del bot"
        verbose_name_plural = "Horarios del bot"
        ordering = ["day_of_week", "start_time"]

    def __str__(self):
        dias = dict(DAY_CHOICES)
        dia = dias.get(self.day_of_week, str(self.day_of_week))
        canal = f" [{self.channel.nombre}]" if self.channel else ""
        modo_label = dict(self.MODO_CHOICES).get(self.modo, self.modo)
        return f"{dia} {self.start_time:%H:%M}-{self.end_time:%H:%M} [{modo_label}]{canal}"


class ConversacionWhatsApp(models.Model):
    ATENCION_BOT = "bot"
    ATENCION_ASESOR = "asesor"
    ATENCION_CERRADA = "cerrada"
    ESTADOS_ATENCION = [
        (ATENCION_BOT, "Bot atendiendo"),
        (ATENCION_ASESOR, "Asesor atendiendo"),
        (ATENCION_CERRADA, "Cerrada"),
    ]

    RECOPILACION_NUEVA = "nueva"
    RECOPILACION_EN_PROCESO = "en_proceso"
    RECOPILACION_ESPERANDO = "esperando_cliente"
    RECOPILACION_COMPLETA = "completa"
    ESTADOS_RECOPILACION = [
        (RECOPILACION_NUEVA, "Nueva"),
        (RECOPILACION_EN_PROCESO, "En proceso"),
        (RECOPILACION_ESPERANDO, "Esperando al cliente"),
        (RECOPILACION_COMPLETA, "Completa"),
    ]

    COTIZACION_SIN_INICIAR = "sin_iniciar"
    COTIZACION_PENDIENTE = "por_cotizar"
    COTIZACION_PRECIO_ENVIADO = "precio_enviado"
    COTIZACION_CERRADA = "cerrada"
    ESTADOS_COTIZACION = [
        (COTIZACION_SIN_INICIAR, "Sin iniciar"),
        (COTIZACION_PENDIENTE, "Por cotizar"),
        (COTIZACION_PRECIO_ENVIADO, "Precio enviado"),
        (COTIZACION_CERRADA, "Cerrada"),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="sesiones_whatsapp",
    )
    lead = models.ForeignKey(
        Lead,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sesiones_whatsapp",
    )
    channel = models.ForeignKey(
        WhatsAppChannel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conversaciones",
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversaciones_whatsapp_asignadas",
    )
    estado_atencion = models.CharField(
        max_length=20,
        choices=ESTADOS_ATENCION,
        default=ATENCION_BOT,
    )
    estado_recopilacion = models.CharField(
        max_length=30,
        choices=ESTADOS_RECOPILACION,
        default=RECOPILACION_NUEVA,
    )
    estado_cotizacion = models.CharField(
        max_length=30,
        choices=ESTADOS_COTIZACION,
        default=COTIZACION_SIN_INICIAR,
    )
    bot_pausado = models.BooleanField(default=False)
    instruccion_retorno_bot = models.CharField(max_length=40, blank=True)
    resumen = models.TextField(blank=True)
    datos_faltantes = models.JSONField(default=list, blank=True)
    porcentaje_informacion = models.PositiveSmallIntegerField(default=0)
    motivo_derivacion = models.TextField(blank=True)
    ultima_actividad = models.DateTimeField(default=timezone.now)
    ultimo_mensaje_cliente = models.DateTimeField(null=True, blank=True)
    ultimo_mensaje_enviado = models.DateTimeField(null=True, blank=True)
    cerrada_en = models.DateTimeField(null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ultima_actividad"]
        constraints = [
            models.UniqueConstraint(
                fields=["lead"],
                condition=models.Q(lead__isnull=False) & ~models.Q(estado_atencion="cerrada"),
                name="whatsapp_lead_conversacion_activa_unica",
            ),
            models.CheckConstraint(
                condition=models.Q(porcentaje_informacion__gte=0)
                & models.Q(porcentaje_informacion__lte=100),
                name="whatsapp_porcentaje_informacion_valido",
            ),
        ]
        indexes = [
            models.Index(fields=["channel", "estado_atencion", "-ultima_actividad"]),
            models.Index(fields=["estado_cotizacion", "-ultima_actividad"]),
        ]

    def __str__(self):
        return f"Conversacion WhatsApp {self.pk} - {self.cliente}"


class MensajeWhatsApp(models.Model):
    ORIGEN_CLIENTE = "cliente"
    ORIGEN_BOT = "bot"
    ORIGEN_ASESOR = "asesor"
    ORIGEN_SISTEMA = "sistema"
    ORIGENES = [
        (ORIGEN_CLIENTE, "Cliente"),
        (ORIGEN_BOT, "Bot"),
        (ORIGEN_ASESOR, "Asesor"),
        (ORIGEN_SISTEMA, "Sistema"),
    ]
    ENTRANTE = "entrante"
    SALIENTE = "saliente"
    DIRECCIONES = [(ENTRANTE, "Entrante"), (SALIENTE, "Saliente")]
    TIPOS = [
        ("texto", "Texto"),
        ("imagen", "Imagen"),
        ("audio", "Audio"),
        ("documento", "Documento"),
        ("ubicacion", "Ubicacion"),
        ("sistema", "Sistema"),
    ]
    ESTADOS = [
        ("recibido", "Recibido"),
        ("pendiente", "Pendiente"),
        ("enviado", "Enviado"),
        ("entregado", "Entregado"),
        ("leido", "Leido"),
        ("error", "Error"),
    ]

    conversacion = models.ForeignKey(
        ConversacionWhatsApp,
        on_delete=models.CASCADE,
        related_name="mensajes",
    )
    meta_message_id = models.CharField(max_length=255, blank=True)
    direccion = models.CharField(max_length=10, choices=DIRECCIONES)
    origen = models.CharField(max_length=10, choices=ORIGENES)
    tipo = models.CharField(max_length=20, choices=TIPOS, default="texto")
    contenido = models.TextField(blank=True)
    evidencia = models.ForeignKey(
        EvidenciaWhatsapp,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensajes",
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensajes_whatsapp",
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    error_codigo = models.CharField(max_length=80, blank=True)
    error_detalle = models.TextField(blank=True)
    fecha_mensaje = models.DateTimeField(default=timezone.now)
    entregado_en = models.DateTimeField(null=True, blank=True)
    leido_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha_mensaje", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["meta_message_id"],
                condition=~models.Q(meta_message_id=""),
                name="whatsapp_meta_message_id_unico",
            ),
        ]
        indexes = [
            models.Index(fields=["conversacion", "fecha_mensaje"]),
            models.Index(fields=["estado", "fecha_mensaje"]),
        ]

    def __str__(self):
        return f"{self.origen} - {self.tipo} - {self.fecha_mensaje:%Y-%m-%d %H:%M}"


class AuditoriaWhatsApp(models.Model):
    conversacion = models.ForeignKey(
        ConversacionWhatsApp,
        on_delete=models.CASCADE,
        related_name="auditoria",
    )
    lead = models.ForeignKey(
        Lead,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auditoria_whatsapp",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_auditoria_whatsapp",
    )
    evento = models.CharField(max_length=80)
    detalle = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["conversacion", "-creado_en"])]

    def __str__(self):
        return f"{self.evento} - {self.creado_en:%Y-%m-%d %H:%M}"
