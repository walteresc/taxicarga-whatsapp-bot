"""API v2 de Planilla — Fase 1: configuración de planilla del trabajador."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.campo.models import Conductor
from apps.planilla.api.mappers import (
    ATTENDANCE_FIELDS, COMPENSATION_FIELDS, CONFIG_FIELDS, PAYMENT_FIELDS,
    api_to_model, model_to_api,
)
from apps.planilla.api.serializers import (
    AttendanceSerializer, CompensationSerializer, PaymentSerializer, PayrollConfigSerializer,
)
from apps.planilla.models import (
    ConfiguracionPlanilla, MovimientoCompensacion, Pago, RegistroAsistencia,
)
from apps.planilla.services import calcular_pago, saldo_horas, vacaciones_info

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
        self.assertEqual(
            set(CompensationSerializer().fields) - {"id", "workerName"}, set(COMPENSATION_FIELDS),
        )
        self.assertEqual(
            set(PaymentSerializer().fields) - {"id", "workerName", "contractType"},
            set(PAYMENT_FIELDS),
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
        # reporte: vacío hasta que se registre a alguien
        r = self.client.get("/api/v2/payroll/day?date=2026-03-10")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["rows"]), 0)

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

    def test_saldo_acumulado_del_mes(self):
        cfg = _config(_conductor())
        for dia, salida in ((5, "18:00"), (6, "17:00")):  # Δ +1 y Δ 0
            self.client.post("/api/v2/payroll/day", {
                "trabajadorId": cfg.id, "fecha": f"2026-03-{dia:02d}",
                "dayType": "trabajado", "clockIn": "08:00", "clockOut": salida,
            }, format="json")
        r = self.client.get("/api/v2/payroll/day?date=2026-03-06")
        self.assertEqual(len(r.data["rows"]), 1)
        self.assertEqual(r.data["rows"][0]["balanceHours"], 1.0)

    def test_clear_borra_el_registro(self):
        cfg = _config(_conductor())
        self.client.post("/api/v2/payroll/day", {
            "trabajadorId": cfg.id, "fecha": "2026-03-10", "dayType": "descanso",
        }, format="json")
        self.client.post("/api/v2/payroll/day", {
            "trabajadorId": cfg.id, "fecha": "2026-03-10", "clear": True,
        }, format="json")
        self.assertFalse(RegistroAsistencia.objects.filter(trabajador=cfg).exists())


class SaldoYCompensacionTests(_Authed):
    def _falta(self, cfg, fecha):
        return RegistroAsistencia.objects.create(
            trabajador=cfg, fecha=fecha, tipo_dia="falta",
            horas_jornada_dia=cfg.horas_jornada, horas_refrigerio_dia=cfg.horas_refrigerio,
        )

    def test_saldo_horas_suma_deltas_y_compensaciones(self):
        cfg = _config(_conductor())
        # 2 días con +2 h cada uno
        for dia in (3, 4):
            RegistroAsistencia.objects.create(
                trabajador=cfg, fecha=dt.date(2026, 4, dia), tipo_dia="trabajado",
                hora_ingreso=dt.time(8, 0), hora_salida=dt.time(19, 0),
                horas_jornada_dia="8.00", horas_refrigerio_dia="1.00",
            )
        self.assertEqual(saldo_horas(cfg, dt.date(2026, 4, 4)), 4)
        MovimientoCompensacion.objects.create(
            trabajador=cfg, fecha=dt.date(2026, 4, 5), tipo="pago_horas", horas="-3.00",
        )
        self.assertEqual(saldo_horas(cfg, dt.date(2026, 4, 5)), 1)

    def test_apertura_manual_arrastra(self):
        cfg = _config(_conductor())
        from apps.planilla.models import SaldoHorasMes
        SaldoHorasMes.objects.create(trabajador=cfg, anio=2026, mes=5, saldo_apertura="6.00")
        self.assertEqual(saldo_horas(cfg, dt.date(2026, 5, 1)), 6)

    def test_compensar_falta_requiere_saldo(self):
        cfg = _config(_conductor())
        falta = self._falta(cfg, dt.date(2026, 4, 10))
        # sin saldo → rechaza
        r = self.client.post("/api/v2/payroll-compensations/", {
            "trabajadorId": cfg.id, "kind": "falta_compensada", "attendanceId": falta.id,
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("hours", r.data["fields"])

        # con saldo de +10 h (un día trabajado largo) → acepta y resta la jornada
        RegistroAsistencia.objects.create(
            trabajador=cfg, fecha=dt.date(2026, 4, 1), tipo_dia="trabajado",
            hora_ingreso=dt.time(6, 0), hora_salida=dt.time(23, 0),
            horas_jornada_dia="8.00", horas_refrigerio_dia="1.00",
        )
        r = self.client.post("/api/v2/payroll-compensations/", {
            "trabajadorId": cfg.id, "kind": "falta_compensada", "attendanceId": falta.id,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        mv = MovimientoCompensacion.objects.get()
        self.assertEqual(mv.horas, -8)  # -jornada
        self.assertEqual(str(mv.fecha), "2026-04-10")

    def test_faltas_pendientes(self):
        cfg = _config(_conductor())
        self._falta(cfg, dt.date(2026, 4, 10))
        r = self.client.get("/api/v2/payroll/pending-absences?from=2026-04-01&to=2026-04-30")
        self.assertEqual(len(r.data), 1)
        self.assertFalse(r.data[0]["compensable"])  # saldo 0 < jornada 8


class PagosTests(_Authed):
    def _trabajado(self, cfg, y, m, d, ci="08:00", co="17:00"):
        return RegistroAsistencia.objects.create(
            trabajador=cfg, fecha=dt.date(y, m, d), tipo_dia="trabajado",
            hora_ingreso=dt.time(*map(int, ci.split(":"))),
            hora_salida=dt.time(*map(int, co.split(":"))),
            horas_jornada_dia="8.00", horas_refrigerio_dia="1.00",
        )

    def test_calc_planilla_fin_de_mes_con_falta(self):
        cfg = _config(_conductor(), monto_mes="1130", pct_afp="10")
        for d in range(2, 22):  # días trabajados
            self._trabajado(cfg, 2026, 3, d)
        RegistroAsistencia.objects.create(
            trabajador=cfg, fecha=dt.date(2026, 3, 25), tipo_dia="falta",
            horas_jornada_dia="8.00", horas_refrigerio_dia="1.00",
        )
        r = calcular_pago(cfg, dt.date(2026, 3, 1), dt.date(2026, 3, 31), "fin_de_mes")
        # bruto = 1130 - 1*(1130/30) = 1092.33 ; afp 10% = 109.23 ; neto = 983.10
        self.assertEqual(r["absencesDeducted"], 1)
        self.assertEqual(r["grossAmount"], 1092.33)
        self.assertEqual(r["afpDeduction"], 109.23)
        self.assertEqual(r["netAmount"], 983.10)
        self.assertEqual(r["valorHora"], 4.7083)

    def test_calc_honorarios_por_dias(self):
        cfg = _config(_conductor(), tipo_contrato="honorarios", monto_mes=None, monto_dia="60")
        for d in (2, 3, 4, 5):
            self._trabajado(cfg, 2026, 3, d)
        r = calcular_pago(cfg, dt.date(2026, 3, 1), dt.date(2026, 3, 31), "fin_de_mes")
        self.assertEqual(r["daysWorked"], 4)
        self.assertEqual(r["grossAmount"], 240.0)
        self.assertEqual(r["afpDeduction"], 0.0)

    def test_registrar_pago_via_api(self):
        cfg = _config(_conductor())
        r = self.client.post("/api/v2/payroll-payments/", {
            "trabajadorId": cfg.id, "type": "quincena",
            "periodFrom": "2026-03-01", "periodTo": "2026-03-15",
            "grossAmount": "565.00", "afpDeduction": "56.50", "netAmount": "508.50",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        p = Pago.objects.get()
        self.assertEqual(str(p.monto_neto), "508.50")
        # marcar pagado por PATCH
        r = self.client.patch(f"/api/v2/payroll-payments/{p.id}/", {
            "paid": True, "paidOn": "2026-03-16",
        }, format="json")
        self.assertEqual(r.status_code, 200)
        p.refresh_from_db()
        self.assertTrue(p.pagado)

    def test_calc_endpoint(self):
        cfg = _config(_conductor(), monto_mes="1200", pct_afp="0")
        r = self.client.get(
            f"/api/v2/payroll/calc?trabajadorId={cfg.id}&from=2026-03-01&to=2026-03-31&type=quincena",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["grossAmount"], 600.0)

    def test_calc_por_dias_trabajador_que_entra_a_mitad_de_mes(self):
        # ingreso el 20, se calcula del 1 al 30 → paga solo del 20 al 30 = 11 días
        cfg = _config(_conductor(), monto_mes="3000", pct_afp="0",
                      fecha_ingreso=dt.date(2026, 3, 20))
        r = calcular_pago(cfg, dt.date(2026, 3, 1), dt.date(2026, 3, 30), "por_dias")
        self.assertEqual(r["payableDays"], 11)
        self.assertEqual(r["grossAmount"], 1100.0)  # 11 * (3000/30)


class VacacionesYResumenTests(_Authed):
    def test_vacaciones_por_anio_cumplido(self):
        cfg = _config(_conductor(), fecha_ingreso=dt.date(2024, 3, 1))
        v = vacaciones_info(cfg, dt.date(2026, 9, 1))  # ~2.5 años
        self.assertEqual(v["yearsCompleted"], 2)
        self.assertEqual(v["daysEarned"], 30)
        self.assertEqual(v["daysPending"], 30)
        self.assertGreater(v["daysAccruedCurrentYear"], 0)

    def test_vacaciones_no_aplica_honorarios(self):
        cfg = _config(_conductor(), tipo_contrato="honorarios", monto_mes=None, monto_dia="60")
        self.assertEqual(vacaciones_info(cfg, dt.date(2026, 9, 1)), {"aplica": False})

    def test_summary_y_worker_detalle(self):
        cfg = _config(_conductor())
        RegistroAsistencia.objects.create(
            trabajador=cfg, fecha=dt.date(2026, 9, 2), tipo_dia="trabajado",
            hora_ingreso=dt.time(8, 0), hora_salida=dt.time(19, 0),
            horas_jornada_dia="8.00", horas_refrigerio_dia="1.00",
        )
        r = self.client.get("/api/v2/payroll/summary?from=2026-09-01&to=2026-09-05")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["rows"]), 1)
        self.assertEqual(r.data["rows"][0]["balanceHours"], 2.0)

        r = self.client.get(f"/api/v2/payroll/worker/{cfg.id}?date=2026-09-05")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["balanceHours"], 2.0)
        self.assertEqual(len(r.data["recentAttendance"]), 1)


class RbacTests(APITestCase):
    def test_sin_rol_403(self):
        u = User.objects.create_user("nr", password="x")
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/payroll-config/").status_code, 403)
        self.assertEqual(self.client.get("/api/v2/payroll/day").status_code, 403)
        self.assertEqual(self.client.get("/api/v2/payroll-payments/").status_code, 403)
        self.assertEqual(self.client.get("/api/v2/payroll/summary").status_code, 403)
