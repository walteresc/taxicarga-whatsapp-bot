"""Modelos de Planilla (payroll) — microempresa peruana.

Fase 1: solo `ConfiguracionPlanilla` (contrato de cada trabajador). La asistencia,
el saldo de horas, las compensaciones y los pagos llegan en fases siguientes.

Un "trabajador" puede ser un Conductor, un Ayudante (ambos en apps.campo) o un
Asesor (un User del grupo "Asesor de Ventas"). El link se hace con 3 FKs
opcionales + `tipo`; un CheckConstraint garantiza que exactamente una calce.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

_ZERO = Decimal("0")
_TREINTA = Decimal("30")


class ConfiguracionPlanilla(models.Model):
    TIPO_CONDUCTOR = "conductor"
    TIPO_AYUDANTE = "ayudante"
    TIPO_ASESOR = "asesor"
    TIPOS = [
        (TIPO_CONDUCTOR, "Conductor"),
        (TIPO_AYUDANTE, "Ayudante"),
        (TIPO_ASESOR, "Asesor"),
    ]

    CONTRATO_HONORARIOS = "honorarios"
    CONTRATO_PLANILLA = "planilla"
    CONTRATOS = [
        (CONTRATO_HONORARIOS, "Recibo por honorarios"),
        (CONTRATO_PLANILLA, "Planilla"),
    ]

    tipo = models.CharField(max_length=12, choices=TIPOS)
    conductor = models.ForeignKey(
        "campo.Conductor", on_delete=models.CASCADE,
        null=True, blank=True, related_name="config_planilla",
    )
    ayudante = models.ForeignKey(
        "campo.Ayudante", on_delete=models.CASCADE,
        null=True, blank=True, related_name="config_planilla",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name="config_planilla",
    )

    horas_jornada = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("8.00"),
        verbose_name="Horas de jornada",
    )
    horas_refrigerio = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("1.00"),
        verbose_name="Horas de refrigerio",
    )
    tipo_contrato = models.CharField(max_length=12, choices=CONTRATOS)
    monto_dia = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Monto por día (honorarios)",
    )
    monto_mes = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Monto por mes (planilla)",
    )
    pct_afp = models.DecimalField(
        max_digits=5, decimal_places=2, default=_ZERO, verbose_name="% AFP",
    )
    fecha_ingreso = models.DateField()
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de planilla"
        verbose_name_plural = "Configuraciones de planilla"
        ordering = ["tipo", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["conductor"], condition=Q(conductor__isnull=False),
                name="planilla_config_conductor_unico",
            ),
            models.UniqueConstraint(
                fields=["ayudante"], condition=Q(ayudante__isnull=False),
                name="planilla_config_ayudante_unico",
            ),
            models.UniqueConstraint(
                fields=["usuario"], condition=Q(usuario__isnull=False),
                name="planilla_config_usuario_unico",
            ),
            models.CheckConstraint(
                name="planilla_config_link_coherente",
                condition=(
                    (Q(tipo="conductor") & Q(conductor__isnull=False)
                     & Q(ayudante__isnull=True) & Q(usuario__isnull=True))
                    | (Q(tipo="ayudante") & Q(ayudante__isnull=False)
                       & Q(conductor__isnull=True) & Q(usuario__isnull=True))
                    | (Q(tipo="asesor") & Q(usuario__isnull=False)
                       & Q(conductor__isnull=True) & Q(ayudante__isnull=True))
                ),
            ),
        ]

    def clean(self):
        if self.tipo_contrato == self.CONTRATO_HONORARIOS and self.monto_dia is None:
            raise ValidationError({"monto_dia": "Requerido para recibo por honorarios."})
        if self.tipo_contrato == self.CONTRATO_PLANILLA and self.monto_mes is None:
            raise ValidationError({"monto_mes": "Requerido para planilla."})

    # ── datos del trabajador vinculado ──────────────────────────────────
    @property
    def persona(self):
        return self.conductor or self.ayudante or self.usuario

    @property
    def worker_id(self):
        if self.tipo == self.TIPO_CONDUCTOR:
            return self.conductor_id
        if self.tipo == self.TIPO_AYUDANTE:
            return self.ayudante_id
        return self.usuario_id

    @property
    def nombre(self):
        p = self.persona
        if p is None:
            return ""
        if self.tipo == self.TIPO_ASESOR:
            return p.get_full_name() or p.username
        return p.nombre

    @property
    def documento(self):
        if self.tipo == self.TIPO_ASESOR:
            return ""
        return getattr(self.persona, "dni", "") or ""

    # ── valorización ───────────────────────────────────────────────────
    @property
    def valor_dia(self):
        if self.tipo_contrato == self.CONTRATO_HONORARIOS:
            return self.monto_dia or _ZERO
        return (self.monto_mes or _ZERO) / _TREINTA

    @property
    def valor_hora(self):
        jornada = self.horas_jornada or _ZERO
        if not jornada:
            return _ZERO
        return self.valor_dia / jornada

    def __str__(self):
        return f"{self.nombre} — {self.get_tipo_contrato_display()}"
