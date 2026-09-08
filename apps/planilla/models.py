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


class RegistroAsistencia(models.Model):
    """Un registro por (trabajador, día). Guarda hora de ingreso/salida y calcula
    en `save()` las horas trabajadas y el Δ contra la jornada (con snapshot de la
    jornada/refrigerio del día para que cambiar la config no reescriba historia).
    """
    TIPO_TRABAJADO = "trabajado"
    TIPO_FALTA = "falta"
    TIPO_VACACIONES = "vacaciones"
    TIPO_DESCANSO = "descanso"
    TIPO_FERIADO = "feriado"
    TIPO_LICENCIA_SG = "licencia_sin_goce"
    TIPOS_DIA = [
        (TIPO_TRABAJADO, "Trabajado"),
        (TIPO_FALTA, "Falta"),
        (TIPO_VACACIONES, "Vacaciones"),
        (TIPO_DESCANSO, "Descanso / franco"),
        (TIPO_FERIADO, "Feriado"),
        (TIPO_LICENCIA_SG, "Licencia sin goce"),
    ]

    trabajador = models.ForeignKey(
        ConfiguracionPlanilla, on_delete=models.PROTECT, related_name="asistencias",
    )
    fecha = models.DateField()
    tipo_dia = models.CharField(max_length=20, choices=TIPOS_DIA, default=TIPO_TRABAJADO)
    hora_ingreso = models.TimeField(null=True, blank=True)
    hora_salida = models.TimeField(null=True, blank=True)
    horas_jornada_dia = models.DecimalField(max_digits=4, decimal_places=2)
    horas_refrigerio_dia = models.DecimalField(max_digits=4, decimal_places=2)
    horas_trabajadas = models.DecimalField(max_digits=5, decimal_places=2, default=_ZERO)
    delta_dia = models.DecimalField(max_digits=6, decimal_places=2, default=_ZERO)
    observacion = models.CharField(max_length=200, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Registro de asistencia"
        verbose_name_plural = "Registros de asistencia"
        ordering = ["-fecha", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["trabajador", "fecha"], name="planilla_asistencia_unica_por_dia",
            ),
        ]

    def recompute(self):
        from datetime import datetime, timedelta

        if self.tipo_dia == self.TIPO_TRABAJADO and self.hora_ingreso and self.hora_salida:
            base = datetime(2000, 1, 1)
            ini = base.replace(
                hour=self.hora_ingreso.hour, minute=self.hora_ingreso.minute,
                second=self.hora_ingreso.second,
            )
            fin = base.replace(
                hour=self.hora_salida.hour, minute=self.hora_salida.minute,
                second=self.hora_salida.second,
            )
            if fin <= ini:
                fin += timedelta(days=1)
            minutos = int((fin - ini).total_seconds() // 60)
            presente = (Decimal(minutos) / Decimal("60")).quantize(Decimal("0.01"))
            self.horas_trabajadas = presente - (self.horas_refrigerio_dia or _ZERO)
            self.delta_dia = self.horas_trabajadas - (self.horas_jornada_dia or _ZERO)
        else:
            self.horas_trabajadas = _ZERO
            self.delta_dia = _ZERO

    def save(self, *args, **kwargs):
        self.recompute()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.trabajador.nombre} — {self.fecha} ({self.get_tipo_dia_display()})"
