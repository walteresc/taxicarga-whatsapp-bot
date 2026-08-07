from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.leads.models import Lead


class ServicioHistorico(models.Model):
    fuente = models.CharField(max_length=40, blank=True)
    referencia_externa = models.CharField(max_length=80, blank=True)
    lead_origen = models.ForeignKey(
        Lead, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="historicos_generados",
    )
    fecha = models.DateField()
    tipo_servicio = models.CharField(max_length=80)
    distrito_origen = models.CharField(max_length=120)
    distrito_destino = models.CharField(max_length=120)
    piso_origen = models.PositiveSmallIntegerField(null=True, blank=True)
    piso_destino = models.PositiveSmallIntegerField(null=True, blank=True)
    ascensor_origen = models.BooleanField(null=True, blank=True)
    ascensor_destino = models.BooleanField(null=True, blank=True)
    lista_objetos = models.TextField(blank=True)
    objetos_pesados = models.TextField(blank=True)
    modalidad_servicio = models.CharField(max_length=80, blank=True)
    requiere_desarmado = models.BooleanField(null=True, blank=True)
    acceso_origen = models.CharField(max_length=120, blank=True)
    acceso_destino = models.CharField(max_length=120, blank=True)
    camion_llega_origen = models.BooleanField(null=True, blank=True)
    camion_llega_destino = models.BooleanField(null=True, blank=True)
    distancia_carga_origen_m = models.PositiveIntegerField(null=True, blank=True)
    distancia_carga_destino_m = models.PositiveIntegerField(null=True, blank=True)
    peso_carga_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    volumen_carga_m3 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    camion_usado = models.CharField(max_length=120, blank=True)
    capacidad_camion = models.CharField(max_length=120, blank=True)
    ayudantes = models.PositiveSmallIntegerField(default=2)
    precio_cotizado = models.DecimalField(max_digits=10, decimal_places=2)
    precio_final = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cerrado = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha"]
        constraints = [
            models.UniqueConstraint(
                fields=["fuente", "referencia_externa"],
                condition=~models.Q(referencia_externa=""),
                name="historico_fuente_referencia_unica",
            ),
            models.UniqueConstraint(
                fields=["lead_origen"],
                condition=~models.Q(lead_origen=None),
                name="historico_lead_origen_unico",
            ),
        ]
        indexes = [
            models.Index(fields=["tipo_servicio", "distrito_origen", "distrito_destino"]),
        ]

    def __str__(self):
        return f"{self.fecha} - {self.distrito_origen} -> {self.distrito_destino}"


class Cotizacion(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="cotizaciones")
    precio_min = models.DecimalField(max_digits=10, decimal_places=2)
    precio_max = models.DecimalField(max_digits=10, decimal_places=2)
    precio_recomendado = models.DecimalField(max_digits=10, decimal_places=2)
    servicios_similares_encontrados = models.PositiveIntegerField(default=0)
    explicacion = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"Cotizacion {self.lead_id} - S/ {self.precio_recomendado}"


class SolicitudCotizacion(models.Model):
    PENDIENTE = "pendiente"
    EN_PROCESO = "en_proceso"
    TERMINADA = "terminada"
    CANCELADA = "cancelada"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (EN_PROCESO, "En proceso"),
        (TERMINADA, "Terminada"),
        (CANCELADA, "Cancelada"),
    ]

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="solicitudes_cotizacion",
    )
    conversacion = models.ForeignKey(
        "whatsapp.ConversacionWhatsApp",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitudes_cotizacion",
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default=PENDIENTE)
    motivo = models.TextField(blank=True)
    datos_faltantes = models.JSONField(default=list, blank=True)
    prioridad = models.CharField(max_length=20, choices=Lead.PRIORIDADES, default=Lead.PRIORIDAD_MEDIA)
    asignada_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitudes_cotizacion_asignadas",
    )
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitudes_cotizacion_creadas",
    )
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)
    resuelta_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-prioridad", "creada_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["lead"],
                condition=models.Q(estado__in=["pendiente", "en_proceso"]),
                name="cotizador_solicitud_activa_unica_por_lead",
            ),
        ]
        indexes = [models.Index(fields=["estado", "prioridad", "creada_en"])]

    def __str__(self):
        return f"Solicitud {self.pk} - Lead {self.lead_id}"


class CotizacionComercial(models.Model):
    ESTADOS = [
        ("borrador", "Borrador"),
        ("enviada", "Enviada"),
        ("entregada", "Entregada"),
        ("en_negociacion", "En negociacion"),
        ("aceptada", "Aceptada"),
        ("rechazada", "Rechazada"),
        ("vencida", "Vencida"),
        ("cancelada", "Cancelada"),
    ]
    ORIGENES = [("bot", "Bot"), ("asesor", "Asesor")]

    codigo = models.CharField(max_length=30, unique=True)
    lead = models.ForeignKey(
        Lead,
        on_delete=models.PROTECT,
        related_name="cotizaciones_comerciales",
    )
    solicitud = models.ForeignKey(
        SolicitudCotizacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cotizaciones",
    )
    channel = models.ForeignKey(
        "whatsapp.WhatsAppChannel",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cotizaciones_comerciales",
    )
    origen = models.CharField(max_length=10, choices=ORIGENES)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="borrador")
    asesor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cotizaciones_comerciales",
    )
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creada_en"]
        indexes = [
            models.Index(fields=["estado", "-creada_en"]),
            models.Index(fields=["channel", "-creada_en"]),
        ]

    def __str__(self):
        return self.codigo


class RevisionCotizacion(models.Model):
    cotizacion = models.ForeignKey(
        CotizacionComercial,
        on_delete=models.CASCADE,
        related_name="revisiones",
    )
    numero = models.PositiveSmallIntegerField()
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revisiones_cotizacion",
    )
    snapshot_servicio = models.JSONField(default=dict)
    precio_sugerido_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_sugerido_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    costo_estimado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    margen_minimo_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    precio_final = models.DecimalField(max_digits=10, decimal_places=2)
    condiciones = models.TextField(blank=True)
    vigencia_dias = models.PositiveSmallIntegerField(default=7)
    observacion_interna = models.TextField(blank=True)
    mensaje_whatsapp = models.TextField(blank=True)
    enviada = models.BooleanField(default=False)
    creada_en = models.DateTimeField(auto_now_add=True)
    enviada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["cotizacion", "numero"],
                name="cotizador_revision_numero_unico",
            ),
            models.CheckConstraint(
                condition=models.Q(precio_final__gt=0),
                name="cotizador_revision_precio_positivo",
            ),
        ]

    def __str__(self):
        return f"{self.cotizacion.codigo} v{self.numero}"

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, enviada=True).exists():
            raise ValidationError("Una revision enviada es inmutable.")
        return super().save(*args, **kwargs)


class EnvioCotizacion(models.Model):
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("enviado", "Enviado"),
        ("entregado", "Entregado"),
        ("leido", "Leido"),
        ("error", "Error"),
    ]

    revision = models.ForeignKey(
        RevisionCotizacion,
        on_delete=models.PROTECT,
        related_name="envios",
    )
    channel = models.ForeignKey(
        "whatsapp.WhatsAppChannel",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="envios_cotizacion",
    )
    meta_message_id = models.CharField(max_length=255, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    intento = models.PositiveSmallIntegerField(default=1)
    error_codigo = models.CharField(max_length=80, blank=True)
    error_detalle = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    entregado_en = models.DateTimeField(null=True, blank=True)
    leido_en = models.DateTimeField(null=True, blank=True)
    proximo_reintento = models.DateTimeField(null=True, blank=True)
    max_intentos = models.PositiveSmallIntegerField(default=3)

    class Meta:
        ordering = ["-creado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["meta_message_id"],
                condition=~models.Q(meta_message_id=""),
                name="cotizador_envio_meta_id_unico",
            ),
        ]

    def __str__(self):
        return f"Envio {self.revision} - {self.estado}"

# Create your models here.
