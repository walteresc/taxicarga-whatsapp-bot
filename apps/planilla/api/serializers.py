"""Serializers de la API v2 de Planilla. Claves inglesas vía `source=`.

El test de ida y vuelta en `tests_api.py` verifica que las claves del serializer
no se desincronizan de `mappers.CONFIG_FIELDS`.
"""
from rest_framework import serializers

from apps.planilla.models import (
    ConfiguracionPlanilla, MovimientoCompensacion, Pago, RegistroAsistencia, SaldoHorasMes,
)

_WORKER_FK = {
    ConfiguracionPlanilla.TIPO_CONDUCTOR: "conductor_id",
    ConfiguracionPlanilla.TIPO_AYUDANTE: "ayudante_id",
    ConfiguracionPlanilla.TIPO_ASESOR: "usuario_id",
}


class PayrollConfigSerializer(serializers.ModelSerializer):
    workerType = serializers.ChoiceField(source="tipo", choices=ConfiguracionPlanilla.TIPOS)
    workerId = serializers.SerializerMethodField()
    workerName = serializers.CharField(source="nombre", read_only=True)
    documentId = serializers.CharField(source="documento", read_only=True)
    workdayHours = serializers.DecimalField(
        source="horas_jornada", max_digits=4, decimal_places=2, required=False,
    )
    lunchHours = serializers.DecimalField(
        source="horas_refrigerio", max_digits=4, decimal_places=2, required=False,
    )
    contractType = serializers.ChoiceField(source="tipo_contrato", choices=ConfiguracionPlanilla.CONTRATOS)
    amountPerDay = serializers.DecimalField(
        source="monto_dia", max_digits=10, decimal_places=2, required=False, allow_null=True,
    )
    amountPerMonth = serializers.DecimalField(
        source="monto_mes", max_digits=10, decimal_places=2, required=False, allow_null=True,
    )
    afpPct = serializers.DecimalField(source="pct_afp", max_digits=5, decimal_places=2, required=False)
    hiredOn = serializers.DateField(source="fecha_ingreso")
    endedOn = serializers.DateField(source="fecha_cese", required=False, allow_null=True)
    active = serializers.BooleanField(source="activo", required=False, default=True)
    notes = serializers.CharField(source="observaciones", required=False, allow_blank=True, default="")
    valorDia = serializers.SerializerMethodField()
    valorHora = serializers.SerializerMethodField()

    class Meta:
        model = ConfiguracionPlanilla
        fields = (
            "id", "workerType", "workerId", "workerName", "documentId",
            "workdayHours", "lunchHours", "contractType", "amountPerDay", "amountPerMonth",
            "afpPct", "hiredOn", "endedOn", "active", "notes", "valorDia", "valorHora",
        )

    def get_workerId(self, obj):
        return obj.worker_id

    def get_valorDia(self, obj):
        return round(obj.valor_dia, 4)

    def get_valorHora(self, obj):
        return round(obj.valor_hora, 4)

    def validate(self, attrs):
        contrato = attrs.get("tipo_contrato") or getattr(self.instance, "tipo_contrato", None)
        monto_dia = attrs.get("monto_dia", getattr(self.instance, "monto_dia", None))
        monto_mes = attrs.get("monto_mes", getattr(self.instance, "monto_mes", None))
        if contrato == ConfiguracionPlanilla.CONTRATO_HONORARIOS and monto_dia is None:
            raise serializers.ValidationError({"amountPerDay": "Requerido para recibo por honorarios."})
        if contrato == ConfiguracionPlanilla.CONTRATO_PLANILLA and monto_mes is None:
            raise serializers.ValidationError({"amountPerMonth": "Requerido para planilla."})
        return attrs

    def create(self, validated_data):
        tipo = validated_data["tipo"]
        raw = self.initial_data.get("workerId")
        try:
            worker_id = int(raw)
        except (TypeError, ValueError):
            raise serializers.ValidationError({"workerId": "Requerido."})
        fk = _WORKER_FK[tipo]
        if ConfiguracionPlanilla.objects.filter(**{fk: worker_id}).exists():
            raise serializers.ValidationError(
                {"workerId": "Este trabajador ya tiene configuración de planilla."},
            )
        validated_data[fk] = worker_id
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("tipo", None)  # el vínculo con el trabajador no cambia
        return super().update(instance, validated_data)


class AttendanceSerializer(serializers.ModelSerializer):
    trabajadorId = serializers.PrimaryKeyRelatedField(source="trabajador", read_only=True)
    workerName = serializers.CharField(source="trabajador.nombre", read_only=True)
    date = serializers.DateField(source="fecha", read_only=True)
    dayType = serializers.CharField(source="tipo_dia", read_only=True)
    clockIn = serializers.TimeField(source="hora_ingreso", format="%H:%M", read_only=True)
    clockOut = serializers.TimeField(source="hora_salida", format="%H:%M", read_only=True)
    workdayHours = serializers.DecimalField(source="horas_jornada_dia", max_digits=4, decimal_places=2, read_only=True)
    lunchHours = serializers.DecimalField(source="horas_refrigerio_dia", max_digits=4, decimal_places=2, read_only=True)
    workedHours = serializers.DecimalField(source="horas_trabajadas", max_digits=5, decimal_places=2, read_only=True)
    delta = serializers.DecimalField(source="delta_dia", max_digits=6, decimal_places=2, read_only=True)
    note = serializers.CharField(source="observacion", read_only=True)

    class Meta:
        model = RegistroAsistencia
        fields = (
            "id", "trabajadorId", "workerName", "date", "dayType", "clockIn", "clockOut",
            "workdayHours", "lunchHours", "workedHours", "delta", "note",
        )


class CompensationSerializer(serializers.ModelSerializer):
    trabajadorId = serializers.PrimaryKeyRelatedField(
        source="trabajador", queryset=ConfiguracionPlanilla.objects.all(),
    )
    workerName = serializers.CharField(source="trabajador.nombre", read_only=True)
    date = serializers.DateField(source="fecha", required=False)
    hours = serializers.DecimalField(source="horas", max_digits=6, decimal_places=2, required=False)
    kind = serializers.ChoiceField(source="tipo", choices=MovimientoCompensacion.TIPOS)
    attendanceId = serializers.PrimaryKeyRelatedField(
        source="asistencia", queryset=RegistroAsistencia.objects.all(),
        required=False, allow_null=True,
    )
    reason = serializers.CharField(source="motivo", required=False, allow_blank=True, default="")

    class Meta:
        model = MovimientoCompensacion
        fields = ("id", "trabajadorId", "workerName", "date", "hours", "kind", "attendanceId", "reason")

    def validate(self, attrs):
        tipo = attrs.get("tipo") or getattr(self.instance, "tipo", None)
        trabajador = attrs.get("trabajador") or getattr(self.instance, "trabajador", None)
        asistencia = attrs.get("asistencia")

        if tipo == MovimientoCompensacion.TIPO_FALTA_COMPENSADA:
            if asistencia is None:
                raise serializers.ValidationError({"attendanceId": "Requerido para compensar una falta."})
            if trabajador and asistencia.trabajador_id != trabajador.id:
                raise serializers.ValidationError({"attendanceId": "La falta no es de este trabajador."})
            if asistencia.tipo_dia != RegistroAsistencia.TIPO_FALTA:
                raise serializers.ValidationError({"attendanceId": "Ese día no está marcado como falta."})
            from apps.planilla.services import saldo_horas
            jornada = asistencia.horas_jornada_dia or trabajador.horas_jornada
            if saldo_horas(trabajador, asistencia.fecha) < jornada:
                raise serializers.ValidationError(
                    {"hours": "El saldo de horas no alcanza para compensar un día completo."},
                )
            attrs["fecha"] = asistencia.fecha
            attrs["horas"] = -jornada
        elif attrs.get("horas") is None and self.instance is None:
            raise serializers.ValidationError({"hours": "Requerido."})
        if attrs.get("fecha") is None and self.instance is None:
            raise serializers.ValidationError({"date": "Requerida."})
        return attrs

    def create(self, validated_data):
        req = self.context.get("request")
        if req and req.user.is_authenticated:
            validated_data["creado_por"] = req.user
        return super().create(validated_data)


class OpeningBalanceSerializer(serializers.ModelSerializer):
    trabajadorId = serializers.PrimaryKeyRelatedField(
        source="trabajador", queryset=ConfiguracionPlanilla.objects.all(),
    )
    workerName = serializers.CharField(source="trabajador.nombre", read_only=True)
    year = serializers.IntegerField(source="anio")
    month = serializers.IntegerField(source="mes")
    openingHours = serializers.DecimalField(source="saldo_apertura", max_digits=7, decimal_places=2)
    note = serializers.CharField(source="nota", required=False, allow_blank=True, default="")

    class Meta:
        model = SaldoHorasMes
        fields = ("id", "trabajadorId", "workerName", "year", "month", "openingHours", "note")

    def create(self, validated_data):
        obj, _ = SaldoHorasMes.objects.update_or_create(
            trabajador=validated_data["trabajador"],
            anio=validated_data["anio"], mes=validated_data["mes"],
            defaults={
                "saldo_apertura": validated_data["saldo_apertura"],
                "nota": validated_data.get("nota", ""),
                "editado_manual": True,
            },
        )
        return obj


class PaymentSerializer(serializers.ModelSerializer):
    trabajadorId = serializers.PrimaryKeyRelatedField(
        source="trabajador", queryset=ConfiguracionPlanilla.objects.all(),
    )
    workerName = serializers.CharField(source="trabajador.nombre", read_only=True)
    contractType = serializers.CharField(source="trabajador.tipo_contrato", read_only=True)
    type = serializers.ChoiceField(source="tipo", choices=Pago.TIPOS)
    periodFrom = serializers.DateField(source="periodo_desde")
    periodTo = serializers.DateField(source="periodo_hasta")
    daysWorked = serializers.IntegerField(source="dias_trabajados", required=False, default=0)
    absencesDeducted = serializers.IntegerField(source="dias_falta_descontados", required=False, default=0)
    grossAmount = serializers.DecimalField(source="monto_bruto", max_digits=10, decimal_places=2)
    afpDeduction = serializers.DecimalField(source="descuento_afp", max_digits=10, decimal_places=2, required=False)
    otherDeductions = serializers.DecimalField(source="otros_descuentos", max_digits=10, decimal_places=2, required=False)
    otherDeductionsReason = serializers.CharField(source="otros_descuentos_motivo", required=False, allow_blank=True, default="")
    netAmount = serializers.DecimalField(source="monto_neto", max_digits=10, decimal_places=2)
    paid = serializers.BooleanField(source="pagado", required=False, default=False)
    paidOn = serializers.DateField(source="fecha_pago", required=False, allow_null=True)
    method = serializers.CharField(source="metodo", required=False, allow_blank=True, default="")
    note = serializers.CharField(source="nota", required=False, allow_blank=True, default="")

    class Meta:
        model = Pago
        fields = (
            "id", "trabajadorId", "workerName", "contractType", "type", "periodFrom", "periodTo",
            "daysWorked", "absencesDeducted", "grossAmount", "afpDeduction", "otherDeductions",
            "otherDeductionsReason", "netAmount", "paid", "paidOn", "method", "note",
        )

    def create(self, validated_data):
        req = self.context.get("request")
        if req and req.user.is_authenticated:
            validated_data["registrado_por"] = req.user
        return super().create(validated_data)
