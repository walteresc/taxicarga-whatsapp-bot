from django.conf import settings
from django.db import models


class Vehiculo(models.Model):
    placa = models.CharField(max_length=20, unique=True)
    marca = models.CharField(max_length=80)
    modelo = models.CharField(max_length=80)
    anio = models.PositiveIntegerField(null=True, blank=True, verbose_name="Año")
    capacidad_toneladas = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Capacidad (t)")
    capacidad_m3 = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Capacidad (m³)")
    fecha_vencimiento_soat = models.DateField(null=True, blank=True, verbose_name="Vencimiento SOAT")
    fecha_vencimiento_rtv = models.DateField(null=True, blank=True, verbose_name="Vencimiento RTV")
    fecha_vencimiento_extintor = models.DateField(null=True, blank=True, verbose_name="Vencimiento Extintor")
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "Vehículo"
        verbose_name_plural = "Vehículos"

    def __str__(self):
        return f"{self.placa} - {self.marca} {self.modelo}"


class Conductor(models.Model):
    LICENCIA_CATEGORIAS = [
        ("A-I", "A-I"),
        ("A-II-a", "A-II-a"),
        ("A-II-b", "A-II-b"),
        ("A-III-a", "A-III-a"),
        ("A-III-b", "A-III-b"),
        ("A-III-c", "A-III-c"),
        ("B-I", "B-I"),
        ("B-II-a", "B-II-a"),
        ("B-II-b", "B-II-b"),
        ("B-II-c", "B-II-c"),
    ]
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="conductores",
    )
    nombre = models.CharField(max_length=160)
    dni = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=30)
    numero_licencia = models.CharField(max_length=40, blank=True, verbose_name="N° Licencia")
    categoria_licencia = models.CharField(max_length=20, choices=LICENCIA_CATEGORIAS, blank=True, verbose_name="Categoría")
    fecha_vencimiento_licencia = models.DateField(null=True, blank=True, verbose_name="Vencimiento Licencia")
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "Conductor"
        verbose_name_plural = "Conductores"

    def __str__(self):
        return f"{self.nombre} ({self.dni})"


class Ayudante(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ayudantes",
    )
    nombre = models.CharField(max_length=160)
    dni = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=30)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "Ayudante"
        verbose_name_plural = "Ayudantes"

    def __str__(self):
        return f"{self.nombre} ({self.dni})"


class EquipoDia(models.Model):
    fecha = models.DateField()
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, related_name="equipos_dia")
    conductor = models.ForeignKey(Conductor, on_delete=models.PROTECT, related_name="equipos_dia")
    ayudantes = models.ManyToManyField(Ayudante, blank=True, related_name="equipos_dia")
    conductores_ayudantes = models.ManyToManyField(
        Conductor, blank=True, related_name="equipos_como_ayudante"
    )
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "Equipo del día"
        verbose_name_plural = "Equipos del día"
        unique_together = ["fecha", "vehiculo", "conductor"]

    def __str__(self):
        return f"{self.fecha} - {self.vehiculo.placa} - {self.conductor.nombre}"


class EquipoFrecuente(models.Model):
    nombre = models.CharField(max_length=120, verbose_name="Nombre / Alias")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, related_name="equipos_frecuentes")
    conductor = models.ForeignKey(Conductor, on_delete=models.PROTECT, related_name="equipos_frecuentes")
    ayudantes = models.ManyToManyField(Ayudante, blank=True, related_name="equipos_frecuentes")
    conductores_ayudantes = models.ManyToManyField(
        Conductor, blank=True, related_name="equipos_frecuentes_como_ayudante",
    )
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Equipo frecuente"
        verbose_name_plural = "Equipos frecuentes"
        ordering = ["orden", "nombre"]

    def __str__(self):
        return f"{self.nombre} — {self.vehiculo.placa}"


class ProgramacionServicio(models.Model):
    ESTADO_PROGRAMADO = "programado"
    ESTADO_EN_RUTA = "en_ruta"
    ESTADO_EN_SERVICIO = "en_servicio"
    ESTADO_FINALIZADO = "finalizado"
    ESTADO_CANCELADO = "cancelado"

    ESTADOS_OPERATIVOS = [
        (ESTADO_PROGRAMADO, "Programado"),
        (ESTADO_EN_RUTA, "En ruta"),
        (ESTADO_EN_SERVICIO, "En servicio"),
        (ESTADO_FINALIZADO, "Finalizado"),
        (ESTADO_CANCELADO, "Cancelado"),
    ]

    servicio = models.ForeignKey(
        "servicios.Servicio",
        on_delete=models.PROTECT,
        related_name="programaciones",
    )
    equipo_dia = models.ForeignKey(
        EquipoDia, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="servicios",
    )
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, related_name="programaciones")
    conductor = models.ForeignKey(Conductor, on_delete=models.PROTECT, related_name="programaciones")
    ayudantes = models.ManyToManyField(Ayudante, blank=True, related_name="programaciones")
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField(null=True, blank=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    estado_operativo = models.CharField(
        max_length=20, choices=ESTADOS_OPERATIVOS, default=ESTADO_PROGRAMADO,
    )
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "Programación de servicio"
        verbose_name_plural = "Programaciones de servicios"
        ordering = ["fecha", "hora_inicio"]

    def __str__(self):
        return f"{self.servicio.codigo} - {self.fecha} {self.hora_inicio}"
