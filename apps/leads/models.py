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

    # Cómo quiere cotizar el cliente (portal / wizard). "por_carga" = describe la
    # carga y el sistema elige el vehículo; "por_vehiculo" = el cliente elige el
    # tipo de vehículo dedicado.
    MODO_COT_POR_CARGA = "por_carga"
    MODO_COT_POR_VEHICULO = "por_vehiculo"
    MODOS_COTIZACION = [
        (MODO_COT_POR_CARGA, "Por carga"),
        (MODO_COT_POR_VEHICULO, "Por vehículo"),
    ]

    CATEGORIAS_CARGA = [
        ("mudanza", "Mudanza, muebles y electrodomésticos"),
        ("cajas", "Cajas, paquetes y bultos"),
        ("mercaderia", "Mercadería comercial"),
        ("maquinaria", "Maquinaria y equipos"),
        ("construccion", "Materiales de construcción"),
        ("agricolas", "Productos agrícolas"),
        ("pallets", "Pallets / parihuelas"),
        ("contenedores", "Contenedores"),
        ("refrigerada", "Carga refrigerada"),
        ("otros", "Otros"),
    ]

    # De dónde entró la carga (para que el asesor "entienda qué hacemos de
    # clientes" — teléfono/correo vs portal vs bot).
    ORIGENES_CARGA = [
        ("bot_whatsapp", "Bot de WhatsApp"),
        ("invitado", "Cotización rápida (invitado)"),
        ("portal_cliente", "Portal del cliente"),
        ("asesor_telefono", "Asesor · teléfono"),
        ("asesor_correo", "Asesor · correo"),
        ("asesor_crm", "Asesor · CRM"),
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

    MOTIVO_PERDIDA_PRECIO = "precio"
    MOTIVO_PERDIDA_TIEMPO = "tiempo_respuesta"
    MOTIVO_PERDIDA_COMPETENCIA = "competencia"
    MOTIVO_PERDIDA_NO_RESPONDE = "no_responde"
    MOTIVO_PERDIDA_FUERA_COBERTURA = "fuera_cobertura"
    MOTIVO_PERDIDA_OTRO = "otro"

    MOTIVOS_PERDIDA = [
        (MOTIVO_PERDIDA_PRECIO, "Precio"),
        (MOTIVO_PERDIDA_TIEMPO, "Tiempo de respuesta"),
        (MOTIVO_PERDIDA_COMPETENCIA, "Competencia"),
        (MOTIVO_PERDIDA_NO_RESPONDE, "No responde"),
        (MOTIVO_PERDIDA_FUERA_COBERTURA, "Fuera de cobertura"),
        (MOTIVO_PERDIDA_OTRO, "Otro"),
    ]

    # Palabras clave -> motivo canónico, para mapear texto libre heredado o de
    # formularios que aún mandan una frase. El detalle original se conserva
    # siempre en `motivo_perdida_detalle`.
    _MOTIVO_PERDIDA_KEYWORDS = (
        (MOTIVO_PERDIDA_PRECIO, ("precio", "caro", "presupuesto", "costo", "barato", "economic")),
        (MOTIVO_PERDIDA_TIEMPO, ("tiempo", "demor", "tard", "respuesta lenta", "lento", "muy tarde", "rapidez")),
        (MOTIVO_PERDIDA_COMPETENCIA, ("competencia", "otro proveedor", "otra empresa", "eligio a otro", "eligió a otro", "contrato a otro")),
        (MOTIVO_PERDIDA_NO_RESPONDE, ("no responde", "no contesta", "no contestó", "dejo de responder", "dejó de responder", "sin respuesta", "no volvio", "no volvió")),
        (MOTIVO_PERDIDA_FUERA_COBERTURA, ("cobertura", "no llegamos", "muy lejos", "fuera de zona", "no cubrimos")),
    )

    @classmethod
    def map_motivo_perdida(cls, texto):
        """Devuelve un código de MOTIVOS_PERDIDA a partir de texto libre.
        Si ya es un código válido, lo devuelve tal cual. Si no reconoce nada,
        devuelve 'otro' (nunca None)."""
        valor = (texto or "").strip().lower()
        if not valor:
            return ""
        codigos = {c for c, _ in cls.MOTIVOS_PERDIDA}
        if valor in codigos:
            return valor
        for codigo, claves in cls._MOTIVO_PERDIDA_KEYWORDS:
            if any(clave in valor for clave in claves):
                return codigo
        return cls.MOTIVO_PERDIDA_OTRO

    codigo = models.CharField(
        max_length=20, unique=True, blank=True, db_index=True,
        help_text="Código único de la carga (CRG-NNNN). El Servicio adopta este mismo código.",
    )
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="leads")
    modo_cotizacion = models.CharField(max_length=16, choices=MODOS_COTIZACION, blank=True)
    categoria_carga = models.CharField(max_length=20, choices=CATEGORIAS_CARGA, blank=True)
    origen_carga = models.CharField(max_length=20, choices=ORIGENES_CARGA, default="bot_whatsapp")
    tipo_servicio = models.CharField(max_length=80, blank=True)
    distrito_origen = models.CharField(max_length=120, blank=True)
    distrito_destino = models.CharField(max_length=120, blank=True)
    direccion_origen = models.CharField(max_length=255, blank=True)
    direccion_destino = models.CharField(max_length=255, blank=True)
    # Estructurados + geolocalización, capturados por el autocompletado de
    # direcciones (Mapbox) en los flujos web (invitado/portal). Quedan en
    # blanco/null cuando la carga viene del bot de WhatsApp (texto libre) o de
    # captura manual del asesor sin autocompletado.
    provincia_origen = models.CharField(max_length=120, blank=True)
    provincia_destino = models.CharField(max_length=120, blank=True)
    region_origen = models.CharField(max_length=120, blank=True)
    region_destino = models.CharField(max_length=120, blank=True)
    lat_origen = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng_origen = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lat_destino = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng_destino = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    piso_origen = models.SmallIntegerField(null=True, blank=True)
    piso_destino = models.SmallIntegerField(null=True, blank=True)
    ascensor_origen = models.BooleanField(null=True, blank=True)
    ascensor_destino = models.BooleanField(null=True, blank=True)
    lista_objetos = models.TextField(blank=True)
    objetos_pesados = models.TextField(blank=True)
    incluye_personal_carga = models.BooleanField(null=True, blank=True)
    cantidad_operarios = models.PositiveSmallIntegerField(null=True, blank=True)
    modalidad_servicio = models.CharField(max_length=80, blank=True)
    requiere_desarmado = models.BooleanField(null=True, blank=True)
    requiere_armado = models.BooleanField(null=True, blank=True)
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
    # Persona de contacto para la reserva (opcional): a veces el cliente reserva
    # pero el que recibe/coordina en el sitio es otra persona.
    persona_contacto = models.CharField(max_length=160, blank=True)
    telefono_contacto = models.CharField(max_length=30, blank=True)
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
    es_interprovincial = models.BooleanField(
        default=False,
        help_text="Ruta fuera de Lima Metropolitana (interprovincial o de provincia). "
                  "La marca la extracción NLU; el cotizador automático no cubre estas rutas.",
    )
    motivo_derivacion = models.TextField(blank=True, null=True)
    bot_pausado = models.BooleanField(default=False)
    fecha_derivacion = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    nota_interna = models.TextField(blank=True)
    motivo_perdida = models.CharField(
        max_length=255, blank=True, choices=MOTIVOS_PERDIDA,
        help_text="Motivo canónico de pérdida (para reportes).",
    )
    motivo_perdida_detalle = models.TextField(
        blank=True,
        help_text="Detalle libre del motivo de pérdida, tal como lo escribió el asesor.",
    )
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
        return f"{self.codigo or self.pk} · {self.cliente} - {ruta}"

    def save(self, *args, **kwargs):
        # El código deriva del PK (único, sin carrera, sin necesidad de transacción).
        asignar_codigo = self._state.adding and not self.codigo
        super().save(*args, **kwargs)
        if asignar_codigo and not self.codigo:
            self.codigo = f"CRG-{self.pk:04d}"
            Lead.objects.filter(pk=self.pk).update(codigo=self.codigo)


class LeadUbicacion(models.Model):
    ORIGEN = "origen"
    PARADA = "parada"
    DESTINO = "destino"
    TIPOS = [
        (ORIGEN, "Origen"),
        (PARADA, "Parada"),
        (DESTINO, "Destino"),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="ubicaciones")
    orden = models.PositiveSmallIntegerField()
    tipo = models.CharField(max_length=12, choices=TIPOS)
    distrito = models.CharField(max_length=120, blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    provincia = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    piso = models.PositiveSmallIntegerField(null=True, blank=True)
    ascensor = models.BooleanField(null=True, blank=True)
    acceso_camion = models.BooleanField(null=True, blank=True)
    distancia_acarreo = models.PositiveIntegerField(null=True, blank=True)
    observaciones_acceso = models.TextField(blank=True)

    class Meta:
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(fields=["lead", "orden"], name="lead_ubicacion_orden_unico"),
            models.UniqueConstraint(
                fields=["lead", "tipo"],
                condition=models.Q(tipo__in=["origen", "destino"]),
                name="lead_ubicacion_extremo_unico",
            ),
        ]
        indexes = [models.Index(fields=["lead", "tipo", "orden"])]

    def __str__(self):
        return f"{self.lead_id}:{self.orden} {self.tipo} {self.distrito}"
