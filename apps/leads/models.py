from django.conf import settings
from django.db import models

from apps.clientes.models import Cliente


class Lead(models.Model):
    NUEVO = "nuevo"
    EN_CONVERSACION = "en_conversacion"
    DATOS_INCOMPLETOS = "datos_incompletos"
    COTIZADO = "cotizado"
    ASIGNADO = "asignado"
    CERRADO = "cerrado"
    PERDIDO = "perdido"

    PRIORIDAD_BAJA = "baja"
    PRIORIDAD_MEDIA = "media"
    PRIORIDAD_ALTA = "alta"
    PRIORIDAD_URGENTE = "urgente"

    ETAPA_COTIZACION = "cotizacion"
    ETAPA_RESERVA = "reserva"
    ETAPA_RESERVADO = "reservado"

    ETAPAS = [
        (ETAPA_COTIZACION, "Cotizacion"),
        (ETAPA_RESERVA, "Reserva"),
        (ETAPA_RESERVADO, "Reservado"),
    ]

    ESTADOS = [
        (NUEVO, "Nuevo"),
        (EN_CONVERSACION, "En conversacion"),
        (DATOS_INCOMPLETOS, "Datos incompletos"),
        (COTIZADO, "Cotizado"),
        (ASIGNADO, "Asignado"),
        (CERRADO, "Cerrado"),
        (PERDIDO, "Perdido"),
    ]

    PRIORIDADES = [
        (PRIORIDAD_BAJA, "Baja"),
        (PRIORIDAD_MEDIA, "Media"),
        (PRIORIDAD_ALTA, "Alta"),
        (PRIORIDAD_URGENTE, "Urgente"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="leads")
    tipo_servicio = models.CharField(max_length=80, blank=True)
    distrito_origen = models.CharField(max_length=120, blank=True)
    distrito_destino = models.CharField(max_length=120, blank=True)
    direccion_origen = models.CharField(max_length=255, blank=True)
    direccion_destino = models.CharField(max_length=255, blank=True)
    piso_origen = models.PositiveSmallIntegerField(null=True, blank=True)
    piso_destino = models.PositiveSmallIntegerField(null=True, blank=True)
    ascensor_origen = models.BooleanField(null=True, blank=True)
    ascensor_destino = models.BooleanField(null=True, blank=True)
    lista_objetos = models.TextField(blank=True)
    objetos_pesados = models.TextField(blank=True)
    incluye_personal_carga = models.BooleanField(null=True, blank=True)
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
    tipo_camion = models.CharField(max_length=120, blank=True)
    capacidad_camion = models.CharField(max_length=120, blank=True)
    fecha_servicio = models.DateField(null=True, blank=True)
    fecha_por_confirmar = models.BooleanField(default=False)
    horario_servicio = models.CharField(max_length=80, blank=True)
    horario_por_confirmar = models.BooleanField(default=False)
    etapa_conversacion = models.CharField(
        max_length=20,
        choices=ETAPAS,
        default=ETAPA_COTIZACION,
    )
    dni_reserva = models.CharField(max_length=20, blank=True)
    estado = models.CharField(max_length=30, choices=ESTADOS, default=NUEVO)
    prioridad = models.CharField(max_length=20, choices=PRIORIDADES, default=PRIORIDAD_MEDIA)
    atencion_humana = models.BooleanField(default=False)
    vendedor_asignado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads_asignados",
    )
    precio_estimado_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_estimado_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_recomendado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_cotizado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_final = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    esperando_motivo_no_reserva = models.BooleanField(default=False)
    requiere_asesor = models.BooleanField(default=False)
    motivo_derivacion = models.TextField(blank=True, null=True)
    bot_pausado = models.BooleanField(default=False)
    fecha_derivacion = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    nota_interna = models.TextField(blank=True)
    motivo_perdida = models.CharField(max_length=255, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_ultimo_seguimiento = models.DateTimeField(null=True, blank=True)
    fecha_proximo_seguimiento = models.DateTimeField(null=True, blank=True)
    whatsapp_channel = models.ForeignKey(
        "whatsapp.WhatsAppChannel",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="leads",
    )
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha_creacion"]

    def __str__(self):
        ruta = f"{self.distrito_origen or '?'} -> {self.distrito_destino or '?'}"
        return f"{self.cliente} - {ruta}"

# Create your models here.
