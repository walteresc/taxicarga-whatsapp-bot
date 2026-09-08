"""Serializers de la API v2 de Planilla. Claves inglesas vía `source=`.

El test de ida y vuelta en `tests_api.py` verifica que las claves del serializer
no se desincronizan de `mappers.CONFIG_FIELDS`.
"""
from rest_framework import serializers

from apps.planilla.models import ConfiguracionPlanilla

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
    active = serializers.BooleanField(source="activo", required=False, default=True)
    notes = serializers.CharField(source="observaciones", required=False, allow_blank=True, default="")
    valorDia = serializers.SerializerMethodField()
    valorHora = serializers.SerializerMethodField()

    class Meta:
        model = ConfiguracionPlanilla
        fields = (
            "id", "workerType", "workerId", "workerName", "documentId",
            "workdayHours", "lunchHours", "contractType", "amountPerDay", "amountPerMonth",
            "afpPct", "hiredOn", "active", "notes", "valorDia", "valorHora",
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
