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
            return Decimal(str(self.monto_dia or 0))
        return Decimal(str(self.monto_mes or 0)) / _TREINTA

    @property
    def valor_hora(self):
        jornada = Decimal(str(self.horas_jornada or 0))
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

        refr = Decimal(str(self.horas_refrigerio_dia or 0))
        jorn = Decimal(str(self.horas_jornada_dia or 0))
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
            self.horas_trabajadas = presente - refr
            self.delta_dia = self.horas_trabajadas - jorn
        else:
            self.horas_trabajadas = _ZERO
            self.delta_dia = _ZERO

    def save(self, *args, **kwargs):
        self.recompute()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.trabajador.nombre} — {self.fecha} ({self.get_tipo_dia_display()})"


class SaldoHorasMes(models.Model):
    """Apertura del saldo de horas de un mes. Solo existe cuando el operador la
    edita a mano (`editado_manual=True`); si no, la apertura se calcula como el
    cierre del mes anterior."""
    trabajador = models.ForeignKey(
        ConfiguracionPlanilla, on_delete=models.PROTECT, related_name="saldos_mes",
    )
    anio = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField()
    saldo_apertura = models.DecimalField(max_digits=7, decimal_places=2, default=_ZERO)
    editado_manual = models.BooleanField(default=True)
    nota = models.CharField(max_length=200, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Saldo de horas del mes"
        verbose_name_plural = "Saldos de horas por mes"
        ordering = ["-anio", "-mes"]
        constraints = [
            models.UniqueConstraint(
                fields=["trabajador", "anio", "mes"], name="planilla_saldo_mes_unico",
            ),
        ]

    def __str__(self):
        return f"{self.trabajador.nombre} — {self.anio}-{self.mes:02d}: {self.saldo_apertura}"


class MovimientoCompensacion(models.Model):
    """Ajuste manual del saldo de horas. `horas` con signo: negativo consume el
    saldo a favor del trabajador (compensar una falta, otorgar día libre, pagar
    horas), positivo lo aumenta (el trabajador repone horas, ajuste)."""
    TIPO_FALTA_COMPENSADA = "falta_compensada"
    TIPO_DIA_LIBRE = "dia_libre"
    TIPO_PAGO_HORAS = "pago_horas"
    TIPO_DEVOLUCION = "devolucion_trabajador"
    TIPO_AJUSTE = "ajuste"
    TIPOS = [
        (TIPO_FALTA_COMPENSADA, "Falta compensada con horas"),
        (TIPO_DIA_LIBRE, "Día libre a cuenta de horas"),
        (TIPO_PAGO_HORAS, "Pago de horas extra"),
        (TIPO_DEVOLUCION, "El trabajador repone horas"),
        (TIPO_AJUSTE, "Ajuste manual"),
    ]

    trabajador = models.ForeignKey(
        ConfiguracionPlanilla, on_delete=models.PROTECT, related_name="compensaciones",
    )
    fecha = models.DateField()
    horas = models.DecimalField(max_digits=6, decimal_places=2)
    tipo = models.CharField(max_length=24, choices=TIPOS)
    asistencia = models.ForeignKey(
        RegistroAsistencia, on_delete=models.PROTECT, null=True, blank=True,
        related_name="compensaciones",
    )
    motivo = models.CharField(max_length=200, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Movimiento de compensación"
        verbose_name_plural = "Movimientos de compensación"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.trabajador.nombre} — {self.fecha}: {self.horas:+} h"


class Pago(models.Model):
    TIPO_QUINCENA = "quincena"
    TIPO_FIN_DE_MES = "fin_de_mes"
    TIPO_ADELANTO = "adelanto"
    TIPOS = [
        (TIPO_QUINCENA, "Quincena"),
        (TIPO_FIN_DE_MES, "Fin de mes"),
        (TIPO_ADELANTO, "Adelanto / otro"),
    ]

    trabajador = models.ForeignKey(
        ConfiguracionPlanilla, on_delete=models.PROTECT, related_name="pagos",
    )
    tipo = models.CharField(max_length=12, choices=TIPOS)
    periodo_desde = models.DateField()
    periodo_hasta = models.DateField()
    dias_trabajados = models.PositiveSmallIntegerField(default=0)
    dias_falta_descontados = models.PositiveSmallIntegerField(default=0)
    monto_bruto = models.DecimalField(max_digits=10, decimal_places=2)
    descuento_afp = models.DecimalField(max_digits=10, decimal_places=2, default=_ZERO)
    otros_descuentos = models.DecimalField(max_digits=10, decimal_places=2, default=_ZERO)
    otros_descuentos_motivo = models.CharField(max_length=200, blank=True)
    monto_neto = models.DecimalField(max_digits=10, decimal_places=2)
    detalle = models.JSONField(default=dict, blank=True)
    pagado = models.BooleanField(default=False)
    fecha_pago = models.DateField(null=True, blank=True)
    metodo = models.CharField(max_length=40, blank=True)
    nota = models.TextField(blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pago de planilla"
        verbose_name_plural = "Pagos de planilla"
        ordering = ["-periodo_hasta", "-id"]

    def __str__(self):
        return f"{self.trabajador.nombre} — {self.get_tipo_display()} {self.periodo_hasta}: S/ {self.monto_neto}"
