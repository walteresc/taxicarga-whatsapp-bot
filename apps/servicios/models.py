from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.leads.models import Lead


SERVICIO_PENDIENTE = "pendiente"
SERVICIO_PROGRAMADO = "programado"
SERVICIO_ASIGNADO = "asignado"
SERVICIO_EN_RUTA = "en_ruta"
SERVICIO_FINALIZADO = "finalizado"
SERVICIO_CANCELADO = "cancelado"

ESTADOS_SERVICIO = [
    (SERVICIO_PENDIENTE, "Pendiente"),
    (SERVICIO_PROGRAMADO, "Programado"),
    (SERVICIO_ASIGNADO, "Asignado"),
    (SERVICIO_EN_RUTA, "En ruta"),
    (SERVICIO_FINALIZADO, "Finalizado"),
    (SERVICIO_CANCELADO, "Cancelado"),
]

TIPO_EMBALAJE_CHOICES = [
    ("sin_embalaje", "Sin embalaje"),
    ("basico", "Embalaje básico"),
    ("muebles", "Embalaje de muebles y artefactos"),
    ("full", "Embalaje full"),
]

TIPO_COMPROBANTE_CHOICES = [
    ("ninguno", "Ninguno"),
    ("boleta", "Boleta"),
    ("factura", "Factura"),
]


class Servicio(models.Model):
    lead_origen = models.OneToOneField(
        Lead, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="servicio_generado",
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="servicios",
    )
    whatsapp_channel = models.ForeignKey(
        "whatsapp.WhatsAppChannel",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="servicios",
    )
    asesor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="servicios_asesorados",
    )
    codigo = models.CharField(max_length=20, unique=True, blank=True)

    # Quién ejecuta el servicio. La regla de ventana horaria la fija al crearse
    # (nocturno → tercerizado); el asesor puede cambiarla mientras no esté asignado.
    MODALIDAD_POR_DEFINIR = "por_definir"
    MODALIDAD_PROPIO = "propio"
    MODALIDAD_TERCERIZADO = "tercerizado"
    MODALIDADES_EJECUCION = [
        (MODALIDAD_POR_DEFINIR, "Por definir"),
        (MODALIDAD_PROPIO, "Nuestro equipo"),
        (MODALIDAD_TERCERIZADO, "Transportistas"),
    ]
    modalidad_ejecucion = models.CharField(
        max_length=12, choices=MODALIDADES_EJECUCION, default=MODALIDAD_PROPIO, db_index=True,
    )

    estado = models.CharField(
        max_length=20, choices=ESTADOS_SERVICIO, default=SERVICIO_PENDIENTE
    )

    motivo_cancelacion = models.TextField(blank=True, null=True)
    atendido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="servicios_atendidos",
    )
    fecha_actualizacion_estado = models.DateTimeField(null=True, blank=True)
    usuario_actualizacion = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="servicios_actualizados",
    )

    # -- Cliente / Origen / Destino --
    tipo_servicio = models.CharField(max_length=80, blank=True)
    distrito_origen = models.CharField(max_length=120, blank=True)
    distrito_destino = models.CharField(max_length=120, blank=True)
    direccion_origen = models.CharField(max_length=255, blank=True, default="")
    direccion_destino = models.CharField(max_length=255, blank=True, default="")
    piso_origen = models.CharField(max_length=20, blank=True, default="")
    piso_destino = models.CharField(max_length=20, blank=True, default="")
    acceso_origen = models.CharField(max_length=120, blank=True)
    acceso_destino = models.CharField(max_length=120, blank=True)
    acceso_origen_opciones = models.JSONField(default=list, blank=True)
    acceso_destino_opciones = models.JSONField(default=list, blank=True)

    # -- Carga --
    detalle_carga = models.TextField(blank=True, default="")
    lista_objetos = models.TextField(blank=True)
    objetos_pesados = models.TextField(blank=True)
    incluye_personal_carga = models.BooleanField(null=True, blank=True)
    cantidad_operarios = models.PositiveSmallIntegerField(null=True, blank=True)
    requiere_desarmado = models.BooleanField(null=True, blank=True)
    requiere_armado = models.BooleanField(null=True, blank=True)
    peso_carga_kg = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    volumen_carga_m3 = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # -- Embalaje --
    tipo_embalaje = models.CharField(
        max_length=20, choices=TIPO_EMBALAJE_CHOICES, default="sin_embalaje"
    )

    # -- Requisitos especiales --
    requisitos_especiales = models.JSONField(default=list, blank=True)

    # -- Comprobante --
    tipo_comprobante = models.CharField(
        max_length=20, choices=TIPO_COMPROBANTE_CHOICES, default="ninguno"
    )

    # -- Hitos comerciales (para reportes de ventas) --
    fecha_confirmacion = models.DateField(
        null=True, blank=True,
        help_text="Fecha en que la venta se confirmó (se creó la reserva desde un lead aceptado).",
    )
    fecha_finalizacion = models.DateField(
        null=True, blank=True,
        help_text="Fecha en que el servicio se marcó como finalizado.",
    )
    es_interprovincial = models.BooleanField(
        default=False,
        help_text="Ruta fuera de Lima Metropolitana. Heredado del lead de origen.",
    )

    # -- Fecha / Hora / Precio --
    fecha_servicio = models.DateField(null=True, blank=True)
    horario_servicio = models.CharField(max_length=80, blank=True, default="")
    precio_cotizado = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    precio_final = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    precio = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # -- Varios --
    dni_ruc = models.CharField(max_length=20, blank=True)
    observaciones = models.TextField(blank=True, default="")
    nota_interna = models.TextField(blank=True)

    # -- Auditoría --
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    # -- Tercerización --
    es_tercerizada = models.BooleanField(default=False, db_index=True)
    transportista_asignado = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="servicios_como_transportista",
        help_text="Cliente (con es_transportista=True) al que se adjudicó esta carga.",
    )
    oferta_ganadora = models.ForeignKey(
        "tercerizacion.OfertaTransportista",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    autoriza_compartir_fotos_transportistas = models.BooleanField(
        default=False,
        help_text="El cliente autorizó compartir las fotos de esta mudanza con el "
                   "transportista que la ejecute. Una autorización por servicio, "
                   "confirmada por el asesor antes de reenviar cualquier foto.",
    )

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Reserva"
        verbose_name_plural = "Reservas"

    def __str__(self):
        return f"{self.codigo} - {self.cliente or self.lead_origen}"

    def save(self, *args, **kwargs):
        if not self.codigo:
            # Código unificado: si viene de un Lead, adopta su CRG-NNNN.
            lead = self.lead_origen if self.lead_origen_id else None
            if lead and lead.codigo:
                self.codigo = lead.codigo
            else:
                last = Servicio.objects.select_for_update().order_by("-id").first()
                next_id = (last.id + 1) if last else 1
                self.codigo = f"SVC-{next_id:04d}"
        # Sella la fecha de finalización la primera vez que el servicio llega a
        # ese estado, sea cual sea la vista que lo cambie.
        if self.estado == SERVICIO_FINALIZADO and self.fecha_finalizacion is None:
            self.fecha_finalizacion = timezone.localdate()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None and "fecha_finalizacion" not in update_fields:
                kwargs["update_fields"] = list(update_fields) + ["fecha_finalizacion"]
        super().save(*args, **kwargs)

    @property
    def total_pagado(self):
        from django.db.models import Sum
        from decimal import Decimal
        pagos_reales = self.pagos.filter(
            concepto__in=['adelanto', 'parcial', 'final']
        ).aggregate(t=Sum('monto'))['t'] or Decimal(0)
        return pagos_reales

    @property
    def total_descuentos(self):
        from django.db.models import Sum
        from decimal import Decimal
        desc = self.pagos.filter(
            concepto__in=['descuento', 'ajuste']
        ).aggregate(t=Sum('monto'))['t'] or Decimal(0)
        return desc

    @property
    def saldo_pendiente(self):
        from decimal import Decimal
        precio = self.precio or Decimal(0)
        return max(precio - self.total_pagado - self.total_descuentos, Decimal(0))

    @property
    def estado_pago(self):
        if not self.precio:
            return "sin_precio"
        if self.saldo_pendiente == 0:
            return "pagado"
        if self.total_pagado > 0 or self.total_descuentos > 0:
            return "amortizado"
        return "pendiente"


CONCEPTO_PAGO_CHOICES = [
    ("adelanto", "Adelanto"),
    ("parcial", "Pago parcial"),
    ("final", "Pago final"),
    ("descuento", "Descuento"),
    ("ajuste", "Ajuste"),
]

METODO_PAGO_CHOICES = [
    ("yape", "Yape"),
    ("plin", "Plin"),
    ("bcp_personal", "BCP Persona Natural"),
    ("bcp_sos", "BCP SOS Empresa"),
    ("otro", "Otro"),
]


class PagoReserva(models.Model):
    servicio = models.ForeignKey(
        Servicio, on_delete=models.CASCADE, related_name="pagos"
    )
    concepto = models.CharField(max_length=20, choices=CONCEPTO_PAGO_CHOICES)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_pago = models.DateTimeField()
    observaciones = models.TextField(blank=True, default="")
    usuario_registro = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_pago"]
        verbose_name = "Pago de reserva"
        verbose_name_plural = "Pagos de reservas"

    def __str__(self):
        return f"{self.servicio.codigo} - {self.get_concepto_display()} S/ {self.monto}"


class ServicioUbicacion(models.Model):
    ORIGEN = "origen"
    PARADA = "parada"
    DESTINO = "destino"
    TIPOS = [
        (ORIGEN, "Origen"),
        (PARADA, "Parada"),
        (DESTINO, "Destino"),
    ]

    servicio = models.ForeignKey(
        Servicio, on_delete=models.CASCADE, related_name="ubicaciones"
    )
    orden = models.PositiveSmallIntegerField()
    tipo = models.CharField(max_length=12, choices=TIPOS)
    distrito = models.CharField(max_length=120, blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    piso = models.PositiveSmallIntegerField(null=True, blank=True)
    ascensor = models.BooleanField(null=True, blank=True)
    acceso_camion = models.BooleanField(null=True, blank=True)
    distancia_acarreo = models.PositiveIntegerField(null=True, blank=True)
    observaciones_acceso = models.TextField(blank=True)

    class Meta:
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["servicio", "orden"], name="servicio_ubicacion_orden_unico"
            ),
            models.UniqueConstraint(
                fields=["servicio", "tipo"],
                condition=models.Q(tipo__in=["origen", "destino"]),
                name="servicio_ubicacion_extremo_unico",
            ),
        ]
        indexes = [models.Index(fields=["servicio", "tipo", "orden"])]

    def __str__(self):
        return f"{self.servicio_id}:{self.orden} {self.tipo} {self.distrito}"


class ConfiguracionOperaciones(models.Model):
    """Ajustes de operaciones (singleton). Ventana nocturna: los servicios en
    ese rango se marcan 'tercerizado' automáticamente al crearse porque el
    equipo propio no trabaja de noche."""

    from datetime import time as _t

    ventana_nocturna_inicio = models.TimeField(default=_t(17, 0))
    ventana_nocturna_fin = models.TimeField(default=_t(7, 0))
    derivar_interprovincial_auto = models.BooleanField(
        default=False,
        help_text="Si está activo, las cargas interprovinciales se publican solas "
                   "a los transportistas (modo de precio abierto) en cuanto tienen "
                   "los datos completos, sin que el asesor las cotice.",
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de operaciones"
        verbose_name_plural = "Configuración de operaciones"

    def __str__(self):
        return f"Ventana nocturna {self.ventana_nocturna_inicio:%H:%M}–{self.ventana_nocturna_fin:%H:%M}"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def es_nocturno(self, hora):
        """True si `hora` (time) cae en la ventana nocturna. Maneja el cruce de
        medianoche (17:00 → 07:00)."""
        if hora is None:
            return False
        ini, fin = self.ventana_nocturna_inicio, self.ventana_nocturna_fin
        if ini <= fin:
            return ini <= hora < fin
        return hora >= ini or hora < fin
