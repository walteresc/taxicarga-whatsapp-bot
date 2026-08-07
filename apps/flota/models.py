from django.db import models


class MantenimientoVehiculo(models.Model):
    vehiculo = models.ForeignKey(
        "campo.Vehiculo",
        on_delete=models.CASCADE,
        related_name="mantenimientos",
    )
    fecha_mantenimiento = models.DateField()
    kilometraje_actual = models.PositiveIntegerField(verbose_name="Kilometraje actual")
    proximo_mantenimiento_km = models.PositiveIntegerField(verbose_name="Próximo mantenimiento (km)")
    descripcion = models.TextField(verbose_name="Trabajo realizado")
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "Mantenimiento de Vehículo"
        verbose_name_plural = "Mantenimientos de Vehículos"
        ordering = ["-fecha_mantenimiento"]

    def __str__(self):
        return f"{self.vehiculo.placa} - {self.fecha_mantenimiento}"
