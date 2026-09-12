from django.conf import settings
from django.db import models


class PublicacionCarga(models.Model):
    """Un 'anuncio' de una carga que se va a tercerizar: código corto + texto
    que el asesor copia y pega a mano en los grupos de WhatsApp de
    transportistas. Fase 3 (bot) usa el código para identificar respuestas."""

    ESTADO_BORRADOR = "borrador"
    ESTADO_ABIERTA = "abierta"          # sinónimo histórico de "publicada"
    ESTADO_PUBLICADA = "publicada"
    ESTADO_CON_OFERTAS = "con_ofertas"
    ESTADO_ADJUDICADA = "adjudicada"
    ESTADO_CANCELADA = "cancelada"
    ESTADO_VENCIDA = "vencida"
    ESTADOS = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_ABIERTA, "Abierta"),
        (ESTADO_PUBLICADA, "Publicada"),
        (ESTADO_CON_OFERTAS, "Con ofertas"),
        (ESTADO_ADJUDICADA, "Adjudicada"),
        (ESTADO_CANCELADA, "Cancelada"),
        (ESTADO_VENCIDA, "Vencida"),
    ]

    # Cómo se publica el precio a los transportistas.
    PRECIO_FIJO = "fijo"                # precio cerrado (aceptado por el cliente) → solo aceptan
    PRECIO_REFERENCIAL = "referencial"  # hay un precio guía → se puede ofertar
    PRECIO_ABIERTO = "abierto"          # sin precio → el transportista propone
    MODOS_PRECIO = [
        (PRECIO_FIJO, "Precio fijo"),
        (PRECIO_REFERENCIAL, "Precio referencial"),
        (PRECIO_ABIERTO, "Abierto (a proponer)"),
    ]
    ALCANCE_TODOS = "todos"
    ALCANCE_RED = "red_confianza"
    ALCANCE_SELECCION = "seleccion"
    ALCANCES = [
        (ALCANCE_TODOS, "Todos los transportistas"),
        (ALCANCE_RED, "Red de confianza"),
        (ALCANCE_SELECCION, "Selección"),
    ]
    ADJ_PRIMERO = "primero_acepta"
    ADJ_CERCANIA = "cercania_compat"
    CRITERIOS_ADJUDICACION = [
        (ADJ_PRIMERO, "Primero que acepta"),
        (ADJ_CERCANIA, "Cercanía + compatibilidad (futuro)"),
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
    modo_precio = models.CharField(max_length=12, choices=MODOS_PRECIO, default=PRECIO_ABIERTO)
    precio_publicado = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Costo objetivo hacia el transportista (no el precio de venta al cliente).",
    )
    alcance = models.CharField(max_length=16, choices=ALCANCES, default=ALCANCE_TODOS)
    vigencia_hasta = models.DateTimeField(null=True, blank=True)
    criterio_adjudicacion = models.CharField(
        max_length=16, choices=CRITERIOS_ADJUDICACION, default=ADJ_PRIMERO,
    )

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

    publicada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    publicada_en = models.DateTimeField(null=True, blank=True)

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
    ESTADO_CONTRAOFERTA_TC = "contraoferta_taxicarga"
    ESTADO_CONTRAOFERTA_TR = "contraoferta_transportista"
    ESTADO_ACEPTADA = "aceptada"
    ESTADO_RECHAZADA = "rechazada"
    ESTADO_RETIRADA = "retirada"
    ESTADO_VENCIDA = "vencida"
    ESTADOS = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_CONTRAOFERTA_TC, "Contraoferta de TaxiCarga"),
        (ESTADO_CONTRAOFERTA_TR, "Contraoferta del transportista"),
        (ESTADO_ACEPTADA, "Aceptada"),
        (ESTADO_RECHAZADA, "Rechazada"),
        (ESTADO_RETIRADA, "Retirada"),
        (ESTADO_VENCIDA, "Vencida"),
    ]

    publicacion = models.ForeignKey(
        PublicacionCarga,
        on_delete=models.CASCADE,
        related_name="ofertas",
    )
    cliente = models.ForeignKey(
        "clientes.Cliente",
        on_delete=models.CASCADE, null=True, blank=True,
        related_name="ofertas_transportista",
        help_text="Contacto de WhatsApp que ofertó (canal whatsapp). NULL si la "
                   "ofertó el asesor por CRM/portal a nombre de un afiliado.",
    )
    transportista = models.ForeignKey(
        "Transportista",
        on_delete=models.CASCADE, null=True, blank=True,
        related_name="ofertas",
        help_text="Transportista afiliado (canal crm/portal, y necesario para adjudicar).",
    )
    transportista_vehiculo = models.ForeignKey(
        "TransportistaVehiculo",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Vehículo con el que cubriría el servicio (se fija al adjudicar).",
    )
    precio_ofertado = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Primer precio que puso el transportista (se conserva).",
    )
    monto_actual = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Último monto vigente de la negociación (contraofertas).",
    )
    fecha_aceptacion = models.DateTimeField(
        null=True, blank=True,
        help_text="Cuándo el transportista aceptó (FIFO para adjudicación 'primero que acepta').",
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
    estado = models.CharField(max_length=30, choices=ESTADOS, default=ESTADO_PENDIENTE)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["precio_ofertado", "creado_en"]
        verbose_name = "Oferta de transportista"
        verbose_name_plural = "Ofertas de transportistas"
        constraints = [
            models.UniqueConstraint(
                fields=["publicacion", "cliente"],
                condition=models.Q(cliente__isnull=False),
                name="una_oferta_por_transportista_por_publicacion",
            ),
            models.UniqueConstraint(
                fields=["publicacion", "transportista"],
                condition=models.Q(transportista__isnull=False),
                name="una_oferta_por_afiliado_por_publicacion",
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
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transportista_perfil",
        help_text="Cuenta de acceso al Portal del Transportista (grupo 'Transportista').",
    )
    es_conductor = models.BooleanField(
        default=False, help_text="El transportista también maneja sus vehículos.",
    )
    activo = models.BooleanField(default=True)
    notas = models.TextField(blank=True)

    # -- Dirección / ubicación (2026-09): al registrarse, el transportista
    # indica su dirección y su ciudad/distrito habitual. Sirve hoy para saber
    # qué afiliados hay en cada ciudad (encomienda interprovincial, Fase B:
    # reparto a domicilio en destino). Más adelante, una app propia del
    # transportista la detectará sola (GPS) — por eso ya se deja lat/lng,
    # aunque hoy se llenen a mano o queden vacíos.
    direccion = models.CharField(max_length=255, blank=True, default="")
    ubicacion_frecuente = models.CharField(
        max_length=120, blank=True, default="", db_index=True,
        help_text="Distrito (Lima) o ciudad donde opera habitualmente. "
                  "Se usa para encontrar afiliados en la ciudad destino de "
                  "una encomienda interprovincial.",
    )
    lat_frecuente = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng_frecuente = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # -- Datos de cobro (para liquidarle lo que la plataforma le debe) --
    BANCOS = [
        ("bcp", "BCP"), ("bbva", "BBVA"), ("interbank", "Interbank"),
        ("scotiabank", "Scotiabank"), ("nacion", "Banco de la Nación"), ("otro", "Otro"),
    ]
    TIPOS_CUENTA = [("ahorros", "Ahorros"), ("corriente", "Corriente")]
    pago_banco = models.CharField(max_length=12, choices=BANCOS, blank=True, default="")
    pago_tipo_cuenta = models.CharField(max_length=10, choices=TIPOS_CUENTA, blank=True, default="")
    pago_numero_cuenta = models.CharField(max_length=30, blank=True, default="")
    pago_cci = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Código de Cuenta Interbancario (20 dígitos) — para transferencias entre bancos.",
    )
    pago_titular = models.CharField(max_length=160, blank=True, default="")
    pago_yape = models.CharField(max_length=20, blank=True, default="", help_text="Número Yape / Plin.")
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

    @classmethod
    def para_ubicacion(cls, ciudad):
        """Afiliados activos cuya ubicación frecuente coincide con `ciudad`
        (distrito o ciudad) — para encontrar quién puede hacer el reparto a
        domicilio en la ciudad destino de una encomienda interprovincial."""
        c = (ciudad or "").strip()
        if not c:
            return cls.objects.none()
        return cls.objects.filter(activo=True, ubicacion_frecuente__icontains=c)


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

    # Fotos del vehículo (2026-09): el transportista las sube desde su portal
    # para que el asesor/despacho vea con qué unidad está tratando. 3 cupos
    # fijos (no una galería) — alcanza para exterior/interior/carrocería y es
    # simple de subir desde el celular.
    foto_1 = models.FileField(upload_to="transportistas/vehiculos/%Y/%m/", null=True, blank=True)
    foto_2 = models.FileField(upload_to="transportistas/vehiculos/%Y/%m/", null=True, blank=True)
    foto_3 = models.FileField(upload_to="transportistas/vehiculos/%Y/%m/", null=True, blank=True)

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


class HiloNegociacion(models.Model):
    """Una mesa de negociación de precio alrededor de una carga (Lead). Dos
    frentes por carga: `venta` (cliente ↔ TaxiCarga) y `compra` (TaxiCarga ↔
    transportista) — puede haber varios hilos `compra`, uno por transportista.
    Canal-agnóstico: los mensajes traen su propio `canal` (crm/portal/whatsapp)."""

    TIPO_VENTA = "venta"
    TIPO_COMPRA = "compra"
    TIPOS = [
        (TIPO_VENTA, "Venta (cliente)"),
        (TIPO_COMPRA, "Compra (transportista)"),
    ]

    ESTADO_ABIERTA = "abierta"
    ESTADO_PAUSADA = "pausada"        # el asesor congeló la mesa (control)
    ESTADO_ACUERDO = "acuerdo"        # hay un monto aceptado
    ESTADO_SIN_ACUERDO = "sin_acuerdo"
    ESTADO_CERRADA = "cerrada"
    ESTADOS = [
        (ESTADO_ABIERTA, "Abierta"),
        (ESTADO_PAUSADA, "Pausada"),
        (ESTADO_ACUERDO, "Con acuerdo"),
        (ESTADO_SIN_ACUERDO, "Sin acuerdo"),
        (ESTADO_CERRADA, "Cerrada"),
    ]

    lead = models.ForeignKey(
        "leads.Lead", on_delete=models.CASCADE, related_name="hilos_negociacion",
    )
    tipo = models.CharField(max_length=8, choices=TIPOS)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=ESTADO_ABIERTA)

    cotizacion = models.ForeignKey(
        "cotizador.CotizacionComercial",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="hilos_negociacion",
    )
    publicacion = models.ForeignKey(
        PublicacionCarga,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="hilos_negociacion",
    )
    contraparte = models.ForeignKey(
        "clientes.Cliente",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="hilos_negociacion",
        help_text="Venta: el cliente. Compra: el contacto de WhatsApp del transportista (si lo hay).",
    )
    transportista = models.ForeignKey(
        "Transportista",
        on_delete=models.CASCADE, null=True, blank=True,
        related_name="hilos_negociacion",
        help_text="Compra: el transportista afiliado con quien se negocia.",
    )

    monto_objetivo = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Venta: precio de venta que busca TaxiCarga. Compra: costo tope.",
    )
    monto_actual = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Última propuesta viva sobre la mesa.",
    )
    monto_acordado = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )

    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", help_text="Asesor que controla el hilo (queda al pausar).",
    )
    motivo_pausa = models.CharField(max_length=200, blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    cerrado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-actualizado_en"]
        verbose_name = "Hilo de negociación"
        verbose_name_plural = "Hilos de negociación"
        constraints = [
            models.UniqueConstraint(
                fields=["lead", "tipo", "contraparte"],
                condition=models.Q(contraparte__isnull=False),
                name="hilo_unico_por_lead_tipo_contraparte",
            ),
            models.UniqueConstraint(
                fields=["lead", "tipo", "transportista"],
                condition=models.Q(transportista__isnull=False),
                name="hilo_compra_unico_por_afiliado",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.lead_id} · {self.get_estado_display()}"


class MensajeNegociacion(models.Model):
    """Un mensaje dentro de un HiloNegociacion. `tipo=propuesta` lleva un monto
    y un estado (pendiente → aceptada/contraofertada/rechazada); esas son las
    únicas transiciones que mueven `monto_acordado` del hilo."""

    EMISOR_CLIENTE = "cliente"
    EMISOR_TAXICARGA = "taxicarga"
    EMISOR_TRANSPORTISTA = "transportista"
    EMISOR_SISTEMA = "sistema"
    EMISORES = [
        (EMISOR_CLIENTE, "Cliente"),
        (EMISOR_TAXICARGA, "TaxiCarga"),
        (EMISOR_TRANSPORTISTA, "Transportista"),
        (EMISOR_SISTEMA, "Sistema"),
    ]

    CANAL_CRM = "crm"
    CANAL_PORTAL = "portal"
    CANAL_WHATSAPP = "whatsapp"
    CANALES = [
        (CANAL_CRM, "CRM"),
        (CANAL_PORTAL, "Portal"),
        (CANAL_WHATSAPP, "WhatsApp"),
    ]

    TIPO_TEXTO = "texto"
    TIPO_PROPUESTA = "propuesta"
    TIPO_SISTEMA = "sistema"
    TIPOS = [
        (TIPO_TEXTO, "Texto"),
        (TIPO_PROPUESTA, "Propuesta"),
        (TIPO_SISTEMA, "Sistema"),
    ]

    PROP_PENDIENTE = "pendiente"
    PROP_ACEPTADA = "aceptada"
    PROP_CONTRAOFERTADA = "contraofertada"
    PROP_RECHAZADA = "rechazada"
    PROP_ESTADOS = [
        (PROP_PENDIENTE, "Pendiente"),
        (PROP_ACEPTADA, "Aceptada"),
        (PROP_CONTRAOFERTADA, "Contraofertada"),
        (PROP_RECHAZADA, "Rechazada"),
    ]

    hilo = models.ForeignKey(
        HiloNegociacion, on_delete=models.CASCADE, related_name="mensajes",
    )
    emisor = models.CharField(max_length=14, choices=EMISORES)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", help_text="Usuario del CRM que tipeó el mensaje, si aplica.",
    )
    canal = models.CharField(max_length=10, choices=CANALES, default=CANAL_CRM)
    tipo = models.CharField(max_length=10, choices=TIPOS, default=TIPO_TEXTO)
    texto = models.TextField(blank=True)
    propuesta_monto = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    propuesta_estado = models.CharField(
        max_length=14, choices=PROP_ESTADOS, blank=True,
    )
    respondido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    respondido_en = models.DateTimeField(null=True, blank=True)
    mensaje_whatsapp = models.ForeignKey(
        "whatsapp.MensajeWhatsApp", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado_en"]
        verbose_name = "Mensaje de negociación"
        verbose_name_plural = "Mensajes de negociación"

    def __str__(self):
        return f"{self.get_emisor_display()}: {self.texto[:40] or self.propuesta_monto}"


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


class TramoComision(models.Model):
    """Un escalón de la tabla de comisiones de la plataforma sobre un servicio
    tercerizado. La comisión baja a medida que sube el monto (10 % de S/ 100 no
    es lo mismo que 10 % de S/ 10 000) y puede ser más alta para ciertas
    categorías de carga (p. ej. mudanzas).

    Resolución: se busca el tramo *activo* de la categoría del servicio cuyo
    rango [monto_desde, monto_hasta) contiene el precio; si no hay ninguno para
    esa categoría, se usa el tramo general (categoria = "").
    """

    CATEGORIA_GENERAL = ""

    categoria = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Categoría de carga a la que aplica este tramo. "
                  "Vacío = tabla general (aplica a cualquier categoría sin tabla propia).",
    )
    monto_desde = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Precio del servicio desde el cual aplica este porcentaje (inclusive).",
    )
    monto_hasta = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Hasta (exclusivo). Vacío = sin tope (de este monto para arriba).",
    )
    porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Comisión de la plataforma sobre el precio del servicio, en %.",
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tramo de comisión"
        verbose_name_plural = "Tabla de comisiones"
        ordering = ["categoria", "monto_desde"]

    def __str__(self):
        cat = self.categoria or "general"
        tope = f"{self.monto_hasta:g}" if self.monto_hasta is not None else "∞"
        return f"[{cat}] S/ {self.monto_desde:g}–{tope}: {self.porcentaje:g}%"


class TarifaCargaParcial(models.Model):
    """Tarifa de carga nacional **parcial/consolidada** (LTL): el transportista
    completa su camión con la carga de nuestro cliente + la suya propia u otros
    clientes, así que cobramos solo por lo que el cliente manda (peso) y no por
    el camión entero — más económico, pero el plazo de entrega es mayor porque
    depende de cuándo el transportista termina de llenar el camión.

    No modelamos la consolidación en sí (es negocio del transportista); solo
    cotizamos: dado un destino y un peso, ¿cuánto cobramos y en cuántos días
    estimamos que llega?

    Resolución (`resolver_tarifa_parcial`): tramo *activo* cuyo `destino` matchea
    (o el general, destino="") y cuyo rango de peso [peso_desde, peso_hasta)
    contiene el peso de la carga. Si no hay ninguno → cotización manual
    (requiere_asesor), igual que cualquier otro hueco de la tabla.
    """

    DESTINO_GENERAL = ""

    destino = models.CharField(
        max_length=120, blank=True, default="",
        help_text="Ciudad o región de destino (p. ej. 'Arequipa'). Vacío = tarifa "
                  "general (aplica a cualquier destino sin tabla propia).",
    )
    peso_desde_kg = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        help_text="Peso de la carga desde el cual aplica este tramo (inclusive), en kg.",
    )
    peso_hasta_kg = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Hasta (exclusivo), en kg. Vacío = sin tope (de este peso para arriba).",
    )
    precio_por_kg = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text="Precio al cliente por kg dentro de este tramo (soles).",
    )
    monto_minimo = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Precio mínimo a cobrar en este tramo, aunque el peso × precio_por_kg "
                  "sea menor (piso para cargas chicas).",
    )
    dias_estimados = models.PositiveSmallIntegerField(
        default=5,
        help_text="Plazo de entrega estimado (días hábiles) para este tramo.",
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tarifa de carga parcial"
        verbose_name_plural = "Tabla de tarifas de carga parcial"
        ordering = ["destino", "peso_desde_kg"]

    def __str__(self):
        dest = self.destino or "general"
        tope = f"{self.peso_hasta_kg:g}" if self.peso_hasta_kg is not None else "∞"
        return f"[{dest}] {self.peso_desde_kg:g}–{tope} kg: S/ {self.precio_por_kg:g}/kg"


class Liquidacion(models.Model):
    """Cuenta de un servicio tercerizado: qué cobró (o cobrará) el cliente, qué
    se pactó con el transportista, y el **neto** entre la plataforma y el
    transportista una vez descontada la comisión.

    `neto` > 0  → la plataforma le paga esa cantidad al transportista.
    `neto` < 0  → el transportista le debe esa cantidad a la plataforma
                  (típico cuando cobró el servicio en efectivo).
    """

    MEDIO_POR_DEFINIR = "por_definir"
    MEDIO_PASARELA = "pasarela"
    MEDIO_TRANSFERENCIA = "transferencia"
    MEDIO_EFECTIVO_TRANSPORTISTA = "efectivo_transportista"
    MEDIOS = [
        (MEDIO_POR_DEFINIR, "Por definir"),
        (MEDIO_PASARELA, "Pasarela (el cliente pagó a la plataforma)"),
        (MEDIO_TRANSFERENCIA, "Transferencia a la plataforma"),
        (MEDIO_EFECTIVO_TRANSPORTISTA, "Efectivo cobrado por el transportista"),
    ]

    ESTADO_PENDIENTE = "pendiente"
    ESTADO_CONCILIADA = "conciliada"
    ESTADO_PAGADA = "pagada"
    ESTADO_ANULADA = "anulada"
    ESTADOS = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_CONCILIADA, "Conciliada (lista para liquidar)"),
        (ESTADO_PAGADA, "Liquidada"),
        (ESTADO_ANULADA, "Anulada"),
    ]

    programacion = models.OneToOneField(
        "campo.ProgramacionServicio", on_delete=models.CASCADE, related_name="liquidacion",
    )
    servicio = models.ForeignKey(
        "servicios.Servicio", on_delete=models.CASCADE, related_name="liquidaciones",
    )
    transportista = models.ForeignKey(
        Transportista, on_delete=models.PROTECT, related_name="liquidaciones",
    )

    precio_servicio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    costo_transportista = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    comision_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    comision_monto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sin_comision = models.BooleanField(default=False)
    exencion_motivo = models.CharField(max_length=200, blank=True, default="")

    medio_cobro_cliente = models.CharField(max_length=24, choices=MEDIOS, default=MEDIO_POR_DEFINIR)
    neto = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Positivo: la plataforma paga al transportista. Negativo: el transportista debe a la plataforma.",
    )

    estado = models.CharField(max_length=12, choices=ESTADOS, default=ESTADO_PENDIENTE)
    lote = models.ForeignKey(
        "tercerizacion.LotePago", on_delete=models.SET_NULL, null=True, blank=True, related_name="liquidaciones",
    )
    fecha_liquidacion = models.DateField(null=True, blank=True)
    referencia_pago = models.CharField(max_length=120, blank=True, default="")
    comprobante = models.CharField(max_length=255, blank=True, default="")
    nota = models.TextField(blank=True, default="")
    liquidado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Liquidación de tercerización"
        verbose_name_plural = "Liquidaciones de tercerización"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.servicio.codigo} · {self.transportista.nombre} · neto S/ {self.neto:g}"

    @property
    def direccion(self):
        if self.neto > 0:
            return "a_favor_transportista"
        if self.neto < 0:
            return "a_favor_plataforma"
        return "sin_movimiento"


class LotePago(models.Model):
    """Un lote para pagarle de una vez a varios transportistas (P6). Agrupa
    liquidaciones a favor del transportista; al marcarse pagado, todas sus
    liquidaciones quedan liquidadas con la misma referencia y fecha."""

    ESTADO_BORRADOR = "borrador"
    ESTADO_PAGADO = "pagado"
    ESTADO_ANULADO = "anulado"
    ESTADOS = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_PAGADO, "Pagado"),
        (ESTADO_ANULADO, "Anulado"),
    ]
    METODO_TRANSFERENCIA = "transferencia"
    METODO_YAPE = "yape"
    METODO_OTRO = "otro"
    METODOS = [(METODO_TRANSFERENCIA, "Transferencia"), (METODO_YAPE, "Yape / Plin"), (METODO_OTRO, "Otro")]

    estado = models.CharField(max_length=10, choices=ESTADOS, default=ESTADO_BORRADOR)
    metodo = models.CharField(max_length=14, choices=METODOS, default=METODO_TRANSFERENCIA)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cantidad = models.PositiveIntegerField(default=0)
    referencia = models.CharField(max_length=120, blank=True, default="")
    fecha_pago = models.DateField(null=True, blank=True)
    nota = models.TextField(blank=True, default="")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    pagado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lote de pago a transportistas"
        verbose_name_plural = "Lotes de pago a transportistas"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Lote #{self.pk} · {self.cantidad} pagos · S/ {self.total:g} · {self.estado}"
