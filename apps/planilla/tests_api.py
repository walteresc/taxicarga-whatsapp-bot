"""API v2 de Planilla — Fase 1: configuración de planilla del trabajador."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.campo.models import Conductor
from apps.planilla.api.mappers import (
    ATTENDANCE_FIELDS, CONFIG_FIELDS, api_to_model, model_to_api,
)
from apps.planilla.api.serializers import AttendanceSerializer, PayrollConfigSerializer
from apps.planilla.models import ConfiguracionPlanilla, RegistroAsistencia

User = get_user_model()

_RO = {"id", "workerId", "workerName", "documentId", "valorDia", "valorHora"}


def _config(conductor, **kw):
    base = dict(
        tipo="conductor", conductor=conductor, tipo_contrato="planilla",
        monto_mes="1130", fecha_ingreso=dt.date(2026, 1, 1),
        horas_jornada="8.00", horas_refrigerio="1.00",
    )
    base.update(kw)
    return ConfiguracionPlanilla.objects.create(**base)


def _conductor(**kw):
    base = dict(nombre="Juan Perez", dni="11111111", telefono="999")
    base.update(kw)
    return Conductor.objects.create(**base)


class MapperRoundTripTests(APITestCase):
    def test_config_ida_y_vuelta(self):
        api = {
            "workerType": "conductor", "workdayHours": "8.00", "lunchHours": "1.00",
            "contractType": "planilla", "amountPerDay": None, "amountPerMonth": "1130.00",
            "afpPct": "10.00", "hiredOn": "2026-01-01", "active": True, "notes": "x",
        }
        model = api_to_model(CONFIG_FIELDS, api)
        self.assertEqual(model_to_api(CONFIG_FIELDS, model), api)

    def test_serializer_expone_las_claves_del_mapa(self):
        self.assertEqual(set(PayrollConfigSerializer().fields) - _RO, set(CONFIG_FIELDS))
        self.assertEqual(
            set(AttendanceSerializer().fields) - {"id", "workerName"}, set(ATTENDANCE_FIELDS),
        )


class _Authed(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("planilla_user", password="x")
        g, _ = Group.objects.get_or_create(name="Supervisor")
        self.user.groups.add(g)
        self.client.force_login(self.user)


class PayrollConfigApiTests(_Authed):
    def test_crear_config_de_conductor_planilla(self):
        c = _conductor()
        r = self.client.post("/api/v2/payroll-config/", {
            "workerType": "conductor", "workerId": c.id,
            "contractType": "planilla", "amountPerMonth": "1130.00",
            "workdayHours": "8.00", "lunchHours": "1.00", "afpPct": "10",
            "hiredOn": "2026-01-01",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        cfg = ConfiguracionPlanilla.objects.get()
        self.assertEqual(cfg.conductor_id, c.id)
        self.assertEqual(cfg.tipo, "conductor")
        # valor_dia = 1130 / 30 = 37.6667 ; valor_hora = /8 = 4.7083
        self.assertEqual(str(round(cfg.valor_dia, 4)), "37.6667")
        self.assertEqual(str(round(cfg.valor_hora, 4)), "4.7083")

    def test_honorarios_exige_monto_dia(self):
        c = _conductor()
        r = self.client.post("/api/v2/payroll-config/", {
            "workerType": "conductor", "workerId": c.id,
            "contractType": "honorarios", "hiredOn": "2026-01-01",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("amountPerDay", r.data["fields"])

    def test_no_dos_configs_para_el_mismo_trabajador(self):
        c = _conductor()
        ConfiguracionPlanilla.objects.create(
            tipo="conductor", conductor=c, tipo_contrato="honorarios",
            monto_dia="50", fecha_ingreso=dt.date(2026, 1, 1),
        )
        r = self.client.post("/api/v2/payroll-config/", {
            "workerType": "conductor", "workerId": c.id,
            "contractType": "honorarios", "amountPerDay": "60", "hiredOn": "2026-01-01",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("workerId", r.data["fields"])

    def test_filtro_por_trabajador(self):
        c1, c2 = _conductor(dni="1"), _conductor(dni="2")
        for c in (c1, c2):
            ConfiguracionPlanilla.objects.create(
                tipo="conductor", conductor=c, tipo_contrato="honorarios",
                monto_dia="50", fecha_ingreso=dt.date(2026, 1, 1),
            )
        r = self.client.get(f"/api/v2/payroll-config/?workerType=conductor&workerId={c1.id}")
        self.assertEqual(len(r.data["results"]), 1)
        self.assertEqual(r.data["results"][0]["workerId"], c1.id)

    def test_toggle_active(self):
        c = _conductor()
        cfg = ConfiguracionPlanilla.objects.create(
            tipo="conductor", conductor=c, tipo_contrato="honorarios",
            monto_dia="50", fecha_ingreso=dt.date(2026, 1, 1),
        )
        r = self.client.post(f"/api/v2/payroll-config/{cfg.id}/toggle-active/")
        self.assertFalse(r.data["active"])

    def test_lista_solo_ingles(self):
        c = _conductor()
        ConfiguracionPlanilla.objects.create(
            tipo="conductor", conductor=c, tipo_contrato="honorarios",
            monto_dia="50", fecha_ingreso=dt.date(2026, 1, 1),
        )
        row = self.client.get("/api/v2/payroll-config/").data["results"][0]
        self.assertIn("contractType", row)
        self.assertNotIn("tipo_contrato", row)
        self.assertNotIn("monto_dia", row)


class AttendanceApiTests(_Authed):
    def test_grilla_del_dia_y_upsert_calcula_delta(self):
        cfg = _config(_conductor())
        # grilla: una fila, sin asistencia todavía
        r = self.client.get("/api/v2/payroll/day?date=2026-03-10")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["rows"]), 1)
        self.assertIsNone(r.data["rows"][0]["attendanceId"])

        # upsert: 08:00–18:00, jornada 8, refrigerio 1 → trabajadas 9, Δ +1
        r = self.client.post("/api/v2/payroll/day", {
            "trabajadorId": cfg.id, "fecha": "2026-03-10", "dayType": "trabajado",
            "clockIn": "08:00", "clockOut": "18:00",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(str(r.data["workedHours"]), "9.00")
        self.assertEqual(str(r.data["delta"]), "1.00")

        # segundo upsert el mismo día no duplica
        self.client.post("/api/v2/payroll/day", {
            "trabajadorId": cfg.id, "fecha": "2026-03-10", "dayType": "falta",
        }, format="json")
        self.assertEqual(RegistroAsistencia.objects.filter(trabajador=cfg, fecha="2026-03-10").count(), 1)
        reg = RegistroAsistencia.objects.get(trabajador=cfg, fecha="2026-03-10")
        self.assertEqual(reg.tipo_dia, "falta")
        self.assertEqual(reg.delta_dia, 0)

    def test_delta_mensual_acumulado(self):
        cfg = _config(_conductor())
        for dia, salida in ((5, "18:00"), (6, "17:00")):  # Δ +1 y Δ 0
            self.client.post("/api/v2/payroll/day", {
                "trabajadorId": cfg.id, "fecha": f"2026-03-{dia:02d}",
                "dayType": "trabajado", "clockIn": "08:00", "clockOut": salida,
            }, format="json")
        r = self.client.get("/api/v2/payroll/day?date=2026-03-06")
        self.assertEqual(r.data["rows"][0]["monthDelta"], 1.0)

    def test_clear_borra_el_registro(self):
        cfg = _config(_conductor())
        self.client.post("/api/v2/payroll/day", {
            "trabajadorId": cfg.id, "fecha": "2026-03-10", "dayType": "descanso",
        }, format="json")
        self.client.post("/api/v2/payroll/day", {
            "trabajadorId": cfg.id, "fecha": "2026-03-10", "clear": True,
        }, format="json")
        self.assertFalse(RegistroAsistencia.objects.filter(trabajador=cfg).exists())


class RbacTests(APITestCase):
    def test_sin_rol_403(self):
        u = User.objects.create_user("nr", password="x")
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/payroll-config/").status_code, 403)
        self.assertEqual(self.client.get("/api/v2/payroll/day").status_code, 403)
