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
    visible_cotizador_publico = models.BooleanField(
        default=False,
        help_text=(
            "Si aparece como opción en el selector de vehículo del cotizador público "
            "de Carga (invitado/portal cliente). Antes era una lista fija en el código "
            "(_VEHICLE_CODES_PUBLICOS) que no se podía tocar desde acá — p. ej. Moto/"
            "Auto/Minivan no aplican a 'carga', y Semitrailer/Camión Remolque son carga "
            "muy pesada/especial que hoy pasa siempre por un asesor, no por el "
            "cotizador rápido. Se deja editable para no tener que tocar código si eso "
            "cambia."
        ),
    )

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
    """Carrocerías que admite una CATEGORÍA de vehículo puntual (un tonelaje
    concreto, p. ej. "Camión 2 ton" vs "Camión 15 ton") — no el tipo de
    vehículo genérico completo. Antes estaba ligada a TipoVehiculo, lo que
    hacía que TODAS las categorías de un mismo tipo (p. ej. todos los
    "Camión", desde 2 hasta 15 ton) compartieran exactamente la misma lista
    de carrocerías — un camión de 2 ton terminaba pudiendo "ofrecer" Volquete
    o Grúa Telescópica, que en la práctica son de camiones mucho más
    pesados. Si una categoría no tiene filas = 'sin carrocería / sin
    restricción'."""

    categoria_vehiculo = models.ForeignKey(
        "CategoriaVehiculo", on_delete=models.CASCADE, related_name="compatibilidades",
    )
    tipo_carroceria = models.ForeignKey(
        TipoCarroceria, on_delete=models.CASCADE, related_name="compatibilidades",
    )

    class Meta:
        verbose_name = "Compatibilidad vehículo–carrocería"
        verbose_name_plural = "Compatibilidades vehículo–carrocería"
        constraints = [
            models.UniqueConstraint(
                fields=["categoria_vehiculo", "tipo_carroceria"], name="catalogo_compat_unica",
            ),
        ]

    def __str__(self):
        return f"{self.categoria_vehiculo} → {self.tipo_carroceria}"


class CategoriaVehiculo(models.Model):
    """Fila de la tabla de categorización peso/capacidad. El sistema asigna la
    categoría al registrar un vehículo según su capacidad de carga (ton)."""

    MENORES = "menores"
    LIVIANOS = "livianos"
    MEDIANOS = "medianos"
    PESADOS = "pesados"
    ESPECIALES = "especiales"
    CATEGORIAS = [
        (MENORES, "Menores"),
        (LIVIANOS, "Livianos"),
        (MEDIANOS, "Medianos"),
        (PESADOS, "Pesados"),
        (ESPECIALES, "Especiales"),
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
