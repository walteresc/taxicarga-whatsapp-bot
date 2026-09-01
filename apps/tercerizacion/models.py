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
