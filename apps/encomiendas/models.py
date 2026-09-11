import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def _token():
    return secrets.token_urlsafe(16)


class ConfiguracionEncomiendas(models.Model):
    """Ajustes de encomiendas (singleton)."""

    comision_cod_porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2, default=3,
        help_text="Comisión de la plataforma sobre lo cobrado contra-entrega, en %.",
    )
    envio_incluido_en_cod = models.BooleanField(
        default=True,
        help_text="Si está activo, el monto contra-entrega incluye el precio del envío "
                  "(la plataforma lo retiene). Si no, el envío se cobra aparte.",
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de encomiendas"
        verbose_name_plural = "Configuración de encomiendas"

    def __str__(self):
        return f"Comisión COD {self.comision_cod_porcentaje}%"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ZonaReparto(models.Model):
    """Un grupo de distritos que se cotiza y rutea como una unidad
    (Lima Centro, Lima Norte, Callao, Balnearios…)."""

    nombre = models.CharField(max_length=60, unique=True)
    distritos = models.JSONField(default=list, help_text="Lista de distritos, en minúsculas.")
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "Zona de reparto"
        verbose_name_plural = "Zonas de reparto"

    def __str__(self):
        return self.nombre

    @classmethod
    def para_distrito(cls, distrito):
        d = (distrito or "").strip().lower()
        if not d:
            return None
        for z in cls.objects.filter(activo=True):
            if d in [x.lower() for x in (z.distritos or [])]:
                return z
        return None


class TarifaZona(models.Model):
    """Precio de un envío entre dos zonas, por nivel de servicio y peso.

    `precio_base` cubre hasta `incluye_kg`; cada kg extra suma `precio_kg_extra`.
    """

    NIVEL_EXPRESS = "express"        # mismo día, punto a punto
    NIVEL_STANDARD = "standard"      # día siguiente, vía hub
    NIVELES = [(NIVEL_EXPRESS, "Express (mismo día)"), (NIVEL_STANDARD, "Standard (día siguiente)")]

    origen = models.ForeignKey(ZonaReparto, on_delete=models.CASCADE, related_name="tarifas_desde")
    destino = models.ForeignKey(ZonaReparto, on_delete=models.CASCADE, related_name="tarifas_hasta")
    nivel = models.CharField(max_length=10, choices=NIVELES, default=NIVEL_EXPRESS)
    precio_base = models.DecimalField(max_digits=8, decimal_places=2)
    incluye_kg = models.DecimalField(max_digits=6, decimal_places=2, default=5)
    precio_kg_extra = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    eta_horas = models.PositiveSmallIntegerField(default=6, help_text="Estimado de entrega, en horas.")
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tarifa de zona"
        verbose_name_plural = "Tarifas de zona"
        constraints = [
            models.UniqueConstraint(fields=["origen", "destino", "nivel"], name="tarifa_zona_unica"),
        ]

    def __str__(self):
        return f"{self.origen} → {self.destino} [{self.nivel}] S/ {self.precio_base:g}"


class PuntoEntregaDestino(models.Model):
    """Catálogo de agencias/afiliados en ciudades de provincia donde el
    destinatario de una encomienda interprovincial recoge su paquete (Fase A,
    asset-light — todavía no hay reparto a domicilio fuera de Lima).

    El formulario de alta busca puntos activos de la ciudad elegida; si no hay
    ninguno, el campo sigue siendo texto libre (`Envio.punto_entrega_destino`).
    """

    ciudad = models.CharField(max_length=120, db_index=True, help_text="Ej. 'Arequipa'. Case-insensitive al buscar.")
    nombre = models.CharField(max_length=160, help_text="Ej. 'Agencia Arequipa Centro'.")
    direccion = models.CharField(max_length=255, blank=True, default="")
    telefono = models.CharField(max_length=30, blank=True, default="")
    horario = models.CharField(max_length=120, blank=True, default="", help_text="Ej. 'Lun-Sáb 9am-7pm'.")
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Punto de entrega en destino"
        verbose_name_plural = "Puntos de entrega en destino"
        ordering = ["ciudad", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.ciudad})"

    @classmethod
    def para_ciudad(cls, ciudad):
        c = (ciudad or "").strip().lower()
        if not c:
            return cls.objects.none()
        return cls.objects.filter(activo=True, ciudad__iexact=c)


class RutaReparto(models.Model):
    """Un conjunto ordenado de envíos que un motorizado reparte en un día."""

    ESTADO_PLANIFICADA = "planificada"
    ESTADO_EN_CURSO = "en_curso"
    ESTADO_CERRADA = "cerrada"
    ESTADOS = [
        (ESTADO_PLANIFICADA, "Planificada"),
        (ESTADO_EN_CURSO, "En curso"),
        (ESTADO_CERRADA, "Cerrada"),
    ]

    codigo = models.CharField(max_length=16, unique=True, blank=True)
    transportista = models.ForeignKey(
        "tercerizacion.Transportista", on_delete=models.PROTECT, related_name="rutas_reparto",
    )
    transportista_vehiculo = models.ForeignKey(
        "tercerizacion.TransportistaVehiculo", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    fecha = models.DateField()
    estado = models.CharField(max_length=12, choices=ESTADOS, default=ESTADO_PLANIFICADA)
    iniciada_en = models.DateTimeField(null=True, blank=True)
    cerrada_en = models.DateTimeField(null=True, blank=True)
    notas = models.TextField(blank=True, default="")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha", "-creado_en"]
        verbose_name = "Ruta de reparto"
        verbose_name_plural = "Rutas de reparto"

    def __str__(self):
        return f"{self.codigo} · {self.fecha} · {self.transportista.nombre}"

    def save(self, *args, **kwargs):
        if not self.codigo:
            super().save(*args, **kwargs)
            self.codigo = f"RUT-{self.pk:05d}"
            return super().save(update_fields=["codigo"])
        return super().save(*args, **kwargs)


class Envio(models.Model):
    NIVEL_EXPRESS = TarifaZona.NIVEL_EXPRESS
    NIVEL_STANDARD = TarifaZona.NIVEL_STANDARD
    # Encomienda a otra ciudad (Fase 3, 2026-09): no usa ZonaReparto/TarifaZona
    # (son solo Lima) — el precio sale de la misma tabla que la carga nacional
    # parcial (`apps.tercerizacion.TarifaCargaParcial`, destino × peso), porque
    # es el mismo tramo troncal consolidado. Ver `services.cotizar`.
    NIVEL_INTERPROVINCIAL = "interprovincial"
    NIVELES = TarifaZona.NIVELES + [(NIVEL_INTERPROVINCIAL, "Interprovincial (a otra ciudad)")]

    ESTADO_REGISTRADO = "registrado"
    ESTADO_ASIGNADO = "asignado"
    ESTADO_RECOGIDO = "recogido"
    ESTADO_EN_RUTA = "en_ruta"
    # Solo interprovincial: el paquete llegó a la ciudad destino y espera en el
    # punto de entrega (agencia/afiliado) — todavía no lo recibió el destinatario.
    ESTADO_EN_DESTINO = "en_destino"
    ESTADO_ENTREGADO = "entregado"
    ESTADO_FALLIDO = "fallido"
    ESTADO_DEVUELTO = "devuelto"
    ESTADO_CANCELADO = "cancelado"
    ESTADOS = [
        (ESTADO_REGISTRADO, "Registrado"),
        (ESTADO_ASIGNADO, "Asignado"),
        (ESTADO_RECOGIDO, "Recogido"),
        (ESTADO_EN_RUTA, "En ruta"),
        (ESTADO_EN_DESTINO, "Llegó a destino (punto de entrega)"),
        (ESTADO_ENTREGADO, "Entregado"),
        (ESTADO_FALLIDO, "No entregado"),
        (ESTADO_DEVUELTO, "Devuelto al remitente"),
        (ESTADO_CANCELADO, "Cancelado"),
    ]
    ABIERTOS = (ESTADO_REGISTRADO, ESTADO_ASIGNADO, ESTADO_RECOGIDO, ESTADO_EN_RUTA, ESTADO_EN_DESTINO)

    codigo = models.CharField(max_length=16, unique=True, blank=True)
    token = models.CharField(max_length=32, unique=True, default=_token, editable=False)
    nivel = models.CharField(max_length=16, choices=NIVELES, default=NIVEL_EXPRESS)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=ESTADO_REGISTRADO, db_index=True)

    # -- Origen del pedido, si vino de la API de socios (P4) --
    socio = models.ForeignKey(
        "partners.SocioComercial", on_delete=models.SET_NULL, null=True, blank=True, related_name="envios",
    )
    external_ref = models.CharField(
        max_length=120, blank=True, default="", help_text="ID del pedido en el sistema del socio.",
    )

    # -- Remitente --
    remitente_nombre = models.CharField(max_length=160)
    remitente_telefono = models.CharField(max_length=30, blank=True, default="")
    origen_distrito = models.CharField(max_length=120)
    origen_direccion = models.CharField(max_length=255)
    origen_referencia = models.CharField(max_length=255, blank=True, default="")
    # Geolocalización opcional (autocompletado de direcciones, Mapbox) — igual
    # que en apps.leads. Sirve para mapas/rutas; no cambia cómo se cotiza.
    origen_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    origen_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # -- Destinatario --
    destinatario_nombre = models.CharField(max_length=160)
    destinatario_telefono = models.CharField(max_length=30, blank=True, default="")
    # Si nivel=interprovincial, este campo es la CIUDAD destino (p. ej.
    # "Arequipa"), no un distrito de Lima — mismo campo, distinto significado
    # según el nivel (así no duplicamos columnas para algo mutuamente excluyente).
    destino_distrito = models.CharField(max_length=120)
    destino_direccion = models.CharField(max_length=255)
    destino_referencia = models.CharField(max_length=255, blank=True, default="")
    destino_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    destino_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    # Solo interprovincial, Fase A (asset-light): nombre/dirección del punto
    # aliado en la ciudad destino donde el destinatario recoge el paquete —
    # todavía no hacemos reparto a domicilio fuera de Lima. Texto libre, pero
    # normalmente elegido del catálogo `PuntoEntregaDestino` de esa ciudad.
    punto_entrega_destino = models.CharField(max_length=255, blank=True, default="")

    # -- Paquete --
    contenido = models.CharField(max_length=255, blank=True, default="")
    peso_kg = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    largo_cm = models.PositiveIntegerField(null=True, blank=True)
    ancho_cm = models.PositiveIntegerField(null=True, blank=True)
    alto_cm = models.PositiveIntegerField(null=True, blank=True)
    valor_declarado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # -- Contra-entrega (COD) --
    es_contraentrega = models.BooleanField(default=False)
    monto_contraentrega = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    COD_EFECTIVO = "efectivo"
    COD_YAPE = "yape"
    COD_TARJETA = "tarjeta"
    COD_MEDIOS = [(COD_EFECTIVO, "Efectivo"), (COD_YAPE, "Yape / Plin"), (COD_TARJETA, "Tarjeta")]
    cod_cobrado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cod_medio = models.CharField(max_length=10, choices=COD_MEDIOS, blank=True, default="")
    cod_cobrado_en = models.DateTimeField(null=True, blank=True)
    cod_comprobante = models.FileField(upload_to="encomiendas/cod/%Y/%m/", null=True, blank=True)
    # neto que la plataforma le debe al remitente por este envío
    cod_a_remitir = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cod_rendido = models.BooleanField(default=False, help_text="El motorizado entregó esta plata a la plataforma.")
    cod_remitido = models.BooleanField(default=False, help_text="La plataforma le pagó al remitente su parte.")
    cod_remitido_ref = models.CharField(max_length=120, blank=True, default="")

    # -- Precio del envío (lo paga el remitente / la tienda) --
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # -- Ejecución --
    transportista = models.ForeignKey(
        "tercerizacion.Transportista", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="envios",
    )
    transportista_vehiculo = models.ForeignKey(
        "tercerizacion.TransportistaVehiculo", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="envios",
    )
    ruta = models.ForeignKey(
        RutaReparto, on_delete=models.SET_NULL, null=True, blank=True, related_name="paradas",
    )
    rendicion = models.ForeignKey(
        "encomiendas.RendicionCaja", on_delete=models.SET_NULL, null=True, blank=True, related_name="envios",
    )
    orden_ruta = models.PositiveSmallIntegerField(default=0)
    recogido_en = models.DateTimeField(null=True, blank=True)
    entregado_en = models.DateTimeField(null=True, blank=True)
    recibido_por = models.CharField(max_length=160, blank=True, default="")
    prueba_foto = models.FileField(upload_to="encomiendas/pod/%Y/%m/", null=True, blank=True)
    prueba_firma = models.TextField(blank=True, default="", help_text="Firma capturada (data URL).")
    motivo_fallo = models.CharField(max_length=200, blank=True, default="")
    intentos_entrega = models.PositiveSmallIntegerField(default=0)

    notas = models.TextField(blank=True, default="")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Envío"
        verbose_name_plural = "Envíos"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.codigo} · {self.origen_distrito} → {self.destino_distrito} · {self.estado}"

    def save(self, *args, **kwargs):
        if not self.codigo:
            super().save(*args, **kwargs)
            self.codigo = f"ENC-{self.pk:05d}"
            return super().save(update_fields=["codigo"])
        return super().save(*args, **kwargs)


class RendicionCaja(models.Model):
    """El motorizado le entrega a la plataforma la plata que cobró contra-entrega.
    Agrupa los envíos COD cobrados y todavía no rendidos de un transportista."""

    ESTADO_PENDIENTE = "pendiente"
    ESTADO_CONCILIADA = "conciliada"
    ESTADOS = [(ESTADO_PENDIENTE, "Pendiente"), (ESTADO_CONCILIADA, "Conciliada")]

    codigo = models.CharField(max_length=16, unique=True, blank=True)
    transportista = models.ForeignKey(
        "tercerizacion.Transportista", on_delete=models.PROTECT, related_name="rendiciones_caja",
    )
    esperado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    entregado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    diferencia = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=ESTADO_PENDIENTE)
    referencia = models.CharField(max_length=120, blank=True, default="")
    nota = models.TextField(blank=True, default="")
    conciliada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    conciliada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = "Rendición de caja"
        verbose_name_plural = "Rendiciones de caja"

    def __str__(self):
        return f"{self.codigo} · {self.transportista.nombre} · S/ {self.esperado:g}"

    def save(self, *args, **kwargs):
        if not self.codigo:
            super().save(*args, **kwargs)
            self.codigo = f"REN-{self.pk:05d}"
            return super().save(update_fields=["codigo"])
        return super().save(*args, **kwargs)


class EventoTracking(models.Model):
    envio = models.ForeignKey(Envio, on_delete=models.CASCADE, related_name="eventos")
    estado = models.CharField(max_length=12, choices=Envio.ESTADOS)
    descripcion = models.CharField(max_length=255, blank=True, default="")
    ubicacion = models.CharField(max_length=120, blank=True, default="")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["creado_en", "id"]
        verbose_name = "Evento de seguimiento"
        verbose_name_plural = "Eventos de seguimiento"

    def __str__(self):
        return f"{self.envio.codigo}: {self.estado} @ {self.creado_en:%d/%m %H:%M}"
