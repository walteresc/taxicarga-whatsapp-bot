"""Catálogo maestro de vehículos: tipos de vehículo, tipos de carrocería, qué
carrocería admite cada vehículo y la tabla de categorización por capacidad.

Datos maestros editables desde Configuración → Catálogo de vehículos. Los usan
el alta de vehículos de transportistas y (más adelante) el paso "Vehículo" al
publicar/derivar una carga.
"""
from django.db import models


class TipoVehiculo(models.Model):
    codigo = models.SlugField(max_length=40, unique=True)
    nombre = models.CharField(max_length=80)
    icono = models.CharField(
        max_length=60, blank=True,
        help_text="Clase de Remix Icon, p. ej. 'ri-truck-line'",
    )
    habilitado = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Tipo de vehículo"
        verbose_name_plural = "Tipos de vehículo"
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class TipoCarroceria(models.Model):
    codigo = models.SlugField(max_length=60, unique=True)
    nombre = models.CharField(max_length=80)
    icono = models.CharField(max_length=60, blank=True)
    habilitado = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Tipo de carrocería"
        verbose_name_plural = "Tipos de carrocería"
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class CompatibilidadCarroceria(models.Model):
    """Carrocerías que admite un tipo de vehículo. Si un tipo no tiene filas =
    'sin carrocería / sin restricción'."""

    tipo_vehiculo = models.ForeignKey(
        TipoVehiculo, on_delete=models.CASCADE, related_name="compatibilidades",
    )
    tipo_carroceria = models.ForeignKey(
        TipoCarroceria, on_delete=models.CASCADE, related_name="compatibilidades",
    )

    class Meta:
        verbose_name = "Compatibilidad vehículo–carrocería"
        verbose_name_plural = "Compatibilidades vehículo–carrocería"
        constraints = [
            models.UniqueConstraint(
                fields=["tipo_vehiculo", "tipo_carroceria"], name="catalogo_compat_unica",
            ),
        ]

    def __str__(self):
        return f"{self.tipo_vehiculo} → {self.tipo_carroceria}"


class CategoriaVehiculo(models.Model):
    """Fila de la tabla de categorización peso/capacidad. El sistema asigna la
    categoría al registrar un vehículo según su capacidad de carga (ton)."""

    LIVIANOS = "livianos"
    MEDIANOS = "medianos"
    PESADOS = "pesados"
    CATEGORIAS = [
        (LIVIANOS, "Livianos"),
        (MEDIANOS, "Medianos"),
        (PESADOS, "Pesados"),
    ]

    tipo_vehiculo = models.ForeignKey(
        TipoVehiculo, on_delete=models.CASCADE, related_name="categorias",
    )
    nombre = models.CharField(max_length=80, help_text="p. ej. 'Camión 6 ton'")
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default=LIVIANOS)
    min_ton = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    max_ton = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    orden = models.PositiveSmallIntegerField(default=0)
    habilitado = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Categoría de vehículo"
        verbose_name_plural = "Categorías de vehículo"
        ordering = ["orden", "id"]

    def __str__(self):
        return f"{self.nombre} ({self.get_categoria_display()})"


def categoria_para_capacidad(tipo_vehiculo_id, capacidad_ton):
    """Devuelve la CategoriaVehiculo que corresponde a `capacidad_ton` para un
    tipo de vehículo, o None. Se usa al registrar un vehículo."""
    if capacidad_ton is None:
        # Tipos sin rango (moto, auto…): primera fila habilitada del tipo.
        return (CategoriaVehiculo.objects
                .filter(tipo_vehiculo_id=tipo_vehiculo_id, habilitado=True)
                .order_by("orden").first())
    # Rangos con bordes solapados en los datos (p. ej. 8–10 y 10–12): gana la
    # fila con el límite inferior más alto que aún contiene la capacidad.
    match = (CategoriaVehiculo.objects
             .filter(tipo_vehiculo_id=tipo_vehiculo_id, habilitado=True)
             .filter(models.Q(min_ton__isnull=True) | models.Q(min_ton__lte=capacidad_ton))
             .filter(models.Q(max_ton__isnull=True) | models.Q(max_ton__gte=capacidad_ton))
             .order_by(models.F("min_ton").desc(nulls_last=True), "orden").first())
    if match is None:
        match = (CategoriaVehiculo.objects
                 .filter(tipo_vehiculo_id=tipo_vehiculo_id, habilitado=True)
                 .order_by("orden").first())
    return match
