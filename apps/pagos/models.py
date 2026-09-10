import secrets

from django.conf import settings
from django.db import models


def _token():
    return secrets.token_urlsafe(24)


class OrdenPago(models.Model):
    """Un intento de cobro por pasarela contra una cuota de un servicio.

    Ciclo: creada → (procesando) → pagada | fallida | expirada. Al pagarse
    genera el `PagoReserva` correspondiente (mismo camino que un pago manual),
    que a su vez salda la cuota.
    """

    ESTADO_CREADA = "creada"
    ESTADO_PROCESANDO = "procesando"
    ESTADO_PAGADA = "pagada"
    ESTADO_FALLIDA = "fallida"
    ESTADO_EXPIRADA = "expirada"
    ESTADO_REEMBOLSADA = "reembolsada"
    ESTADOS = [
        (ESTADO_CREADA, "Creada"),
        (ESTADO_PROCESANDO, "Procesando"),
        (ESTADO_PAGADA, "Pagada"),
        (ESTADO_FALLIDA, "Fallida"),
        (ESTADO_EXPIRADA, "Expirada"),
        (ESTADO_REEMBOLSADA, "Reembolsada"),
    ]

    servicio = models.ForeignKey(
        "servicios.Servicio", on_delete=models.CASCADE, related_name="ordenes_pago",
    )
    cuota = models.ForeignKey(
        "servicios.CuotaServicio", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ordenes_pago",
    )
    concepto = models.CharField(max_length=20, default="parcial")
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    moneda = models.CharField(max_length=3, default="PEN")
    email_pagador = models.EmailField(blank=True, default="")

    pasarela = models.CharField(max_length=20, default="fake")
    token = models.CharField(max_length=64, unique=True, default=_token, editable=False)
    external_id = models.CharField(max_length=120, blank=True, default="")
    estado = models.CharField(max_length=12, choices=ESTADOS, default=ESTADO_CREADA)
    intentos = models.PositiveSmallIntegerField(default=0)
    detalle_error = models.CharField(max_length=300, blank=True, default="")
    respuesta = models.JSONField(default=dict, blank=True)

    pago_generado = models.OneToOneField(
        "servicios.PagoReserva", on_delete=models.SET_NULL, null=True, blank=True, related_name="orden_pago",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    origen = models.CharField(max_length=16, default="link")  # link | portal
    expira_en = models.DateTimeField(null=True, blank=True)
    pagado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Orden de pago"
        verbose_name_plural = "Órdenes de pago"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.servicio.codigo} · S/ {self.monto:g} · {self.estado}"

    @property
    def pagable(self):
        from django.utils import timezone
        if self.estado not in (self.ESTADO_CREADA, self.ESTADO_PROCESANDO, self.ESTADO_FALLIDA):
            return False
        return not (self.expira_en and self.expira_en < timezone.now())
