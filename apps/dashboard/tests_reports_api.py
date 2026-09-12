"""API v2 de Reportes — envoltorio inglés sobre services_reportes."""
import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente
from apps.cotizador.models import ServicioHistorico
from apps.servicios.models import Servicio, SERVICIO_FINALIZADO

User = get_user_model()


class _ConAcceso(APITestCase):
    """Analítica es Gerencia/Despacho/Finanzas — a propósito SIN Supervisor
    (decisión del usuario, 2026-09-12). Se usa Despacho para las pruebas de
    la lógica del reporte en sí; el acceso de cada rol se prueba en RbacTests."""

    def setUp(self):
        self.user = User.objects.create_user("rep_user", password="x")
        g, _ = Group.objects.get_or_create(name="Despacho")
        self.user.groups.add(g)
        self.client.force_login(self.user)


class BenchmarkApiTests(_ConAcceso):
    def test_claves_en_ingles_y_sin_reventar_vacio(self):
        r = self.client.get("/api/v2/reports/benchmark")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.data) >= {"total", "closed", "scope", "interprovincialRoutes", "price"}, True)
        self.assertNotIn("cerrados", r.data)
        self.assertEqual(r.data["total"], 0)

    def test_con_datos(self):
        for _ in range(3):
            ServicioHistorico.objects.create(
                fecha=dt.date(2025, 6, 1), tipo_servicio="carga",
                distrito_origen="Lima", distrito_destino="Piura ciudad",
                precio_cotizado=Decimal("2000"), precio_final=Decimal("2000"), cerrado=True,
            )
        r = self.client.get("/api/v2/reports/benchmark")
        self.assertEqual(r.data["closed"], 3)
        self.assertEqual(r.data["scope"]["interprovincial"]["count"], 3)
        route = r.data["interprovincialRoutes"][0]
        self.assertIn("route", route)
        self.assertIn("typicalPrice", route)


class SalesApiTests(_ConAcceso):
    def test_estructura_ingles_vacia(self):
        r = self.client.get("/api/v2/reports/sales?period=month")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.data) >= {"sales", "funnel", "ticket", "collections", "filterOptions"}, True)
        self.assertEqual(r.data["sales"]["gross"]["count"], 0)
        self.assertEqual(r.data["funnel"]["created"], 0)
        self.assertIn("advisors", r.data["filterOptions"])

    def test_con_una_venta(self):
        cli = Cliente.objects.create(nombre="C", telefono="+51900000099")
        hoy = dt.date.today()
        Servicio.objects.create(
            cliente=cli, estado=SERVICIO_FINALIZADO, fecha_confirmacion=hoy,
            tipo_servicio="mudanza", es_interprovincial=False,
            precio=Decimal("600"), precio_final=Decimal("600"),
        )
        r = self.client.get("/api/v2/reports/sales?period=month")
        self.assertEqual(r.data["sales"]["net"]["count"], 1)
        self.assertEqual(r.data["sales"]["net"]["billed"], 600.0)
        self.assertEqual(r.data["ticket"]["local"]["count"], 1)

    def test_filtros_no_revientan(self):
        for qs in ("?period=day", "?period=week", "?period=fortnight",
                   "?period=range&from=2015-01-01&to=2026-12-31",
                   "?period=month&advisor=999&channel=999&type=x"):
            self.assertEqual(self.client.get(f"/api/v2/reports/sales{qs}").status_code, 200, qs)


class RbacTests(APITestCase):
    def test_anonimo(self):
        self.assertIn(self.client.get("/api/v2/reports/benchmark").status_code, (401, 403))

    def test_asesor_de_ventas_no_entra(self):
        u = User.objects.create_user("a", password="x")
        g, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        u.groups.add(g)
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/reports/sales").status_code, 403)

    def test_superusuario_entra(self):
        u = User.objects.create_superuser("su", "s@x.com", "x")
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/reports/benchmark").status_code, 200)

    def test_supervisor_ya_no_entra(self):
        # Decisión del usuario (2026-09-12): Supervisor ve todo el flujo
        # operativo pero no Finanzas/Analítica/Configuración.
        u = User.objects.create_user("sup_sin_acceso", password="x")
        g, _ = Group.objects.get_or_create(name="Supervisor")
        u.groups.add(g)
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/reports/benchmark").status_code, 403)

    def test_gerencia_entra_por_el_bypass(self):
        u = User.objects.create_user("ger_sin_lista", password="x")
        g, _ = Group.objects.get_or_create(name="Gerencia")
        u.groups.add(g)
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/reports/benchmark").status_code, 200)

    def test_finanzas_entra(self):
        u = User.objects.create_user("fin_test", password="x")
        g, _ = Group.objects.get_or_create(name="Finanzas")
        u.groups.add(g)
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/reports/benchmark").status_code, 200)
