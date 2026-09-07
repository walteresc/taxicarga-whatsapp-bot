from django.conf import settings
from django.db import models


class PublicacionCarga(models.Model):
    """Un 'anuncio' de una carga que se va a tercerizar: código corto + texto
    que el asesor copia y pega a mano en los grupos de WhatsApp de
    transportistas. Fase 3 (bot) usa el código para identificar respuestas."""

    ESTADO_ABIERTA = "abierta"
    ESTADO_ADJUDICADA = "adjudicada"
    ESTADO_CANCELADA = "cancelada"
    ESTADOS = [
        (ESTADO_ABIERTA, "Abierta"),
        (ESTADO_ADJUDICADA, "Adjudicada"),
        (ESTADO_CANCELADA, "Cancelada"),
    ]

    servicio = models.ForeignKey(
        "servicios.Servicio",
        on_delete=models.CASCADE,
        related_name="publicaciones_tercerizacion",
    )
    codigo = models.CharField(max_length=10, unique=True, db_index=True)
    texto_publicado = models.TextField(
        help_text="Snapshot del texto generado al momento de publicar. No "
                   "garantiza que sea lo pegado tal cual — el asesor puede "
                   "editarlo antes de pegarlo en el grupo.",
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_ABIERTA)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publicaciones_tercerizacion_creadas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    grupos_publicados = models.JSONField(
        default=list,
        blank=True,
        help_text="Nombres de grupos donde el asesor marcó que pegó la "
                   "publicación. Autoreportado, no verificable por la API.",
    )

    oferta_ganadora = models.ForeignKey(
        "OfertaTransportista",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    adjudicada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    adjudicada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = "Publicación de carga"
        verbose_name_plural = "Publicaciones de carga"

    def __str__(self):
        return f"OFERTA-{self.codigo} ({self.get_estado_display()})"


class OfertaTransportista(models.Model):
    """Una oferta/postura de un transportista sobre una PublicacionCarga.
    El transportista es un Cliente con es_transportista=True (mismo modelo,
    mismo pipeline de mensajería que un cliente normal)."""

    ESTADO_PENDIENTE = "pendiente"
    ESTADO_ACEPTADA = "aceptada"
    ESTADO_RECHAZADA = "rechazada"
    ESTADO_RETIRADA = "retirada"
    ESTADOS = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_ACEPTADA, "Aceptada"),
        (ESTADO_RECHAZADA, "Rechazada"),
        (ESTADO_RETIRADA, "Retirada"),
    ]

    publicacion = models.ForeignKey(
        PublicacionCarga,
        on_delete=models.CASCADE,
        related_name="ofertas",
    )
    cliente = models.ForeignKey(
        "clientes.Cliente",
        on_delete=models.CASCADE,
        related_name="ofertas_transportista",
    )
    precio_ofertado = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    mensaje_origen = models.ForeignKey(
        "whatsapp.MensajeWhatsApp",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Mensaje donde el transportista declaró el precio — "
                   "evidencia/trazabilidad, no se duplica el texto aquí.",
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_PENDIENTE)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["precio_ofertado", "creado_en"]
        verbose_name = "Oferta de transportista"
        verbose_name_plural = "Ofertas de transportistas"
        constraints = [
            models.UniqueConstraint(
                fields=["publicacion", "cliente"],
                name="una_oferta_por_transportista_por_publicacion",
            ),
        ]

    def __str__(self):
        return f"{self.cliente} - {self.publicacion.codigo} - S/ {self.precio_ofertado or '?'}"


class TransportistaBotState(models.Model):
    """Estado conversacional del bot de transportistas (Fase 3) — separado por
    completo de BotConversationState (bot de clientes, whatsapp_bot_v4). Vive
    en su propia tabla a propósito: no comparte máquina de estados ni lógica
    con el bot que cotiza clientes."""

    PASO_ESPERANDO_CODIGO = "esperando_codigo"
    PASO_ESPERANDO_INTENCION = "esperando_intencion"
    PASO_RECOGIENDO_PRECIO = "recogiendo_precio"
    PASO_CONVERSANDO = "conversando"
    PASOS = [
        (PASO_ESPERANDO_CODIGO, "Esperando código"),
        (PASO_ESPERANDO_INTENCION, "Esperando ofertar/consultar"),
        (PASO_RECOGIENDO_PRECIO, "Recogiendo precio"),
        (PASO_CONVERSANDO, "Conversando"),
    ]

    conversacion = models.OneToOneField(
        "whatsapp.ConversacionWhatsApp",
        on_delete=models.CASCADE,
        related_name="estado_bot_transportista",
    )
    publicacion_activa = models.ForeignKey(
        PublicacionCarga,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Sobre qué OFERTA-<código> versa la conversación ahora mismo. "
                   "NULL = todavía no se identificó ninguna (o se perdió el "
                   "contexto) — en ese estado el bot nunca responde, cede al "
                   "asesor.",
    )
    paso = models.CharField(max_length=30, choices=PASOS, default=PASO_ESPERANDO_CODIGO)
    pausado = models.BooleanField(
        default=False,
        help_text="Silencia el bot SOLO para esta conversación — override "
                   "manual del asesor, independiente del interruptor global "
                   "de transportistas y del pausado general del sistema.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Estado del bot de transportistas"
        verbose_name_plural = "Estados del bot de transportistas"

    def __str__(self):
        return f"Conv {self.conversacion_id} - {self.paso}"


# --------------------------------------------------------------------------- #
#  Transportistas afiliados (registro propio: sus vehículos y conductores)
# --------------------------------------------------------------------------- #

class Transportista(models.Model):
    """Transportista externo dado de alta en la app. Puede tener uno o más
    vehículos y uno o más conductores; también puede ser el conductor de sus
    propios vehículos."""

    nombre = models.CharField(max_length=160, help_text="Razón social o nombre")
    documento = models.CharField(max_length=20, blank=True, help_text="RUC o DNI")
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    cliente = models.ForeignKey(
        "clientes.Cliente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transportistas_afiliados",
        help_text="Contacto de WhatsApp asociado, si existe.",
    )
    es_conductor = models.BooleanField(
        default=False, help_text="El transportista también maneja sus vehículos.",
    )
    activo = models.BooleanField(default=True)
    notas = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Transportista afiliado"
        verbose_name_plural = "Transportistas afiliados"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class TransportistaVehiculo(models.Model):
    """Vehículo de un transportista externo. Datos mínimos para la derivación."""

    transportista = models.ForeignKey(
        Transportista, on_delete=models.CASCADE, related_name="vehiculos",
    )
    placa = models.CharField(max_length=20, unique=True)
    tipo_vehiculo = models.ForeignKey(
        "catalogo.TipoVehiculo", on_delete=models.PROTECT, related_name="+",
    )
    tipo_carroceria = models.ForeignKey(
        "catalogo.TipoCarroceria", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    marca = models.CharField(max_length=80, blank=True)
    modelo = models.CharField(max_length=80, blank=True)
    anio = models.PositiveIntegerField(null=True, blank=True, verbose_name="Año")
    capacidad_util_ton = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True, verbose_name="Capacidad útil (ton)",
    )
    largo_util_m = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Largo útil (m)",
    )
    ancho_util_m = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Ancho útil (m)",
    )
    alto_util_m = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Alto útil (m)",
    )
    categoria = models.ForeignKey(
        "catalogo.CategoriaVehiculo",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Se asigna automáticamente según la capacidad útil.",
    )
    activo = models.BooleanField(default=True)
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vehículo de transportista"
        verbose_name_plural = "Vehículos de transportistas"
        ordering = ["placa"]

    def __str__(self):
        return f"{self.placa} ({self.tipo_vehiculo_id})"

    def save(self, *args, **kwargs):
        from apps.catalogo.models import categoria_para_capacidad
        if self.tipo_vehiculo_id:
            self.categoria = categoria_para_capacidad(self.tipo_vehiculo_id, self.capacidad_util_ton)
        super().save(*args, **kwargs)


class TransportistaConductor(models.Model):
    """Conductor de un transportista externo. MODELADO — sin UI todavía."""

    LICENCIA_CATEGORIAS = [
        ("A-I", "A-I"), ("A-II-a", "A-II-a"), ("A-II-b", "A-II-b"),
        ("A-III-a", "A-III-a"), ("A-III-b", "A-III-b"), ("A-III-c", "A-III-c"),
        ("B-I", "B-I"), ("B-II-a", "B-II-a"), ("B-II-b", "B-II-b"), ("B-II-c", "B-II-c"),
    ]

    transportista = models.ForeignKey(
        Transportista, on_delete=models.CASCADE, related_name="conductores",
    )
    nombre = models.CharField(max_length=160)
    dni = models.CharField(max_length=20)
    telefono = models.CharField(max_length=30, blank=True)
    numero_licencia = models.CharField(max_length=40, blank=True, verbose_name="N° Licencia")
    categoria_licencia = models.CharField(
        max_length=20, choices=LICENCIA_CATEGORIAS, blank=True, verbose_name="Categoría",
    )
    fecha_vencimiento_licencia = models.DateField(
        null=True, blank=True, verbose_name="Vencimiento Licencia",
    )
    es_titular = models.BooleanField(
        default=False, help_text="Es el propio transportista.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Conductor de transportista"
        verbose_name_plural = "Conductores de transportistas"
        constraints = [
            models.UniqueConstraint(
                fields=["transportista", "dni"], name="tercerizacion_conductor_dni_por_transportista",
            ),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.dni})"
