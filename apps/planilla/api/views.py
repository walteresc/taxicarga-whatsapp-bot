"""Viewsets y vistas de la API v2 de Planilla."""
from datetime import date as _date, datetime

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler
from apps.api.permissions import HasAnyRole
from apps.api.views import V2ModelViewSet
from apps.planilla.models import ConfiguracionPlanilla, RegistroAsistencia
from apps.planilla.services import (
    attendance_queryset, configs_queryset, dia_planilla, upsert_asistencia,
)

from .serializers import AttendanceSerializer, PayrollConfigSerializer

_ROLES = ("Administrador", "Supervisor", "Asesor de Ventas")


class PayrollConfigViewSet(V2ModelViewSet):
    serializer_class = PayrollConfigSerializer
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        return configs_queryset(self.request.query_params)

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        obj = self.get_object()
        obj.activo = not obj.activo
        obj.save(update_fields=["activo"])
        return Response(self.get_serializer(obj).data)


class AttendanceViewSet(V2ModelViewSet):
    """Solo lectura + borrado. Las altas/ediciones van por POST /payroll/day."""
    serializer_class = AttendanceSerializer
    permission_classes = [HasAnyRole(*_ROLES)]
    http_method_names = ["get", "delete", "head", "options"]

    def get_queryset(self):
        return attendance_queryset(self.request.query_params)


class PayrollDayView(APIView):
    """Grilla de asistencia de un día:
        GET  /api/v2/payroll/day?date=YYYY-MM-DD
        POST /api/v2/payroll/day  {trabajadorId, fecha, dayType, clockIn?, clockOut?, note?}
             o  {trabajadorId, fecha, clear: true}  para borrar el registro del día
    """
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        raw = (request.query_params.get("date") or "").strip()
        try:
            day = _date.fromisoformat(raw) if raw else timezone.localdate()
        except ValueError:
            day = timezone.localdate()
        return Response({"date": day.isoformat(), "rows": dia_planilla(day)})

    def post(self, request):
        d = request.data
        cfg = get_object_or_404(ConfiguracionPlanilla, pk=d.get("trabajadorId"))
        try:
            fecha = _date.fromisoformat(d["fecha"])
        except (KeyError, ValueError, TypeError):
            return Response({"error": "Fecha inválida.", "fields": {"fecha": ["Requerida."]}}, status=400)

        if d.get("clear"):
            RegistroAsistencia.objects.filter(trabajador=cfg, fecha=fecha).delete()
            return Response({"ok": True, "cleared": True})

        tipo = (d.get("dayType") or RegistroAsistencia.TIPO_TRABAJADO).strip()
        if tipo not in {t for t, _ in RegistroAsistencia.TIPOS_DIA}:
            return Response({"error": "Tipo de día no válido.", "fields": {"dayType": ["No válido."]}}, status=400)

        def _t(v):
            if not v:
                return None
            try:
                return datetime.strptime(v, "%H:%M").time()
            except ValueError:
                return None

        reg = upsert_asistencia(
            trabajador=cfg, fecha=fecha, tipo_dia=tipo,
            hora_ingreso=_t(d.get("clockIn")), hora_salida=_t(d.get("clockOut")),
            observacion=d.get("note", ""),
            usuario=request.user if request.user.is_authenticated else None,
        )
        return Response(AttendanceSerializer(reg).data)
