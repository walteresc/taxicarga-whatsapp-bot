from django.db import models

from apps.leads.models import Lead


class ServicioHistorico(models.Model):
    fuente = models.CharField(max_length=40, blank=True)
    referencia_externa = models.CharField(max_length=80, blank=True)
    lead_origen = models.ForeignKey(
        Lead, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="historicos_generados",
    )
    fecha = models.DateField()
    tipo_servicio = models.CharField(max_length=80)
    distrito_origen = models.CharField(max_length=120)
    distrito_destino = models.CharField(max_length=120)
    piso_origen = models.PositiveSmallIntegerField(null=True, blank=True)
    piso_destino = models.PositiveSmallIntegerField(null=True, blank=True)
    ascensor_origen = models.BooleanField(null=True, blank=True)
    ascensor_destino = models.BooleanField(null=True, blank=True)
    lista_objetos = models.TextField(blank=True)
    objetos_pesados = models.TextField(blank=True)
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
    camion_usado = models.CharField(max_length=120, blank=True)
    capacidad_camion = models.CharField(max_length=120, blank=True)
    ayudantes = models.PositiveSmallIntegerField(default=2)
    precio_cotizado = models.DecimalField(max_digits=10, decimal_places=2)
    precio_final = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cerrado = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha"]
        constraints = [
            models.UniqueConstraint(
                fields=["fuente", "referencia_externa"],
                condition=~models.Q(referencia_externa=""),
                name="historico_fuente_referencia_unica",
            ),
            models.UniqueConstraint(
                fields=["lead_origen"],
                condition=~models.Q(lead_origen=None),
                name="historico_lead_origen_unico",
            ),
        ]
        indexes = [
            models.Index(fields=["tipo_servicio", "distrito_origen", "distrito_destino"]),
        ]

    def __str__(self):
        return f"{self.fecha} - {self.distrito_origen} -> {self.distrito_destino}"


class Cotizacion(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="cotizaciones")
    precio_min = models.DecimalField(max_digits=10, decimal_places=2)
    precio_max = models.DecimalField(max_digits=10, decimal_places=2)
    precio_recomendado = models.DecimalField(max_digits=10, decimal_places=2)
    servicios_similares_encontrados = models.PositiveIntegerField(default=0)
    explicacion = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"Cotizacion {self.lead_id} - S/ {self.precio_recomendado}"

# Create your models here.
