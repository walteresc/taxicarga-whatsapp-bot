"""Rentabilidad de la tercerización: precio al cliente = costo + markup, y el
gate de margen mínimo al adjudicar."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.catalogo.models import TipoVehiculo
from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.servicios.models import ConfiguracionOperaciones, Servicio
from apps.tercerizacion import adjudicacion as adj
from apps.tercerizacion.models import (
    PublicacionCarga, TramoComision, Transportista, TransportistaVehiculo,
)
from apps.tercerizacion.services import (
    comision_pct, desglose_comision, evaluar_margen_tercerizacion, precio_cliente_sugerido,
)

User = get_user_model()


def _pub(n, *, precio=None):
    cli = Cliente.objects.create(nombre=f"C{n}", telefono=f"+51944{n:06d}")
    lead = Lead.objects.create(cliente=cli, tipo_servicio="carga",
                               distrito_origen="Lima", distrito_destino="Piura")
    svc = Servicio.objects.create(
        lead_origen=lead, cliente=cli, distrito_origen="Lima", distrito_destino="Piura",
        fecha_servicio=date.today() + timedelta(days=3), horario_servicio="09:00",
        precio=precio, modalidad_ejecucion=Servicio.MODALIDAD_TERCERIZADO,
    )
    pub = PublicacionCarga.objects.create(
        servicio=svc, codigo=f"R{n:02d}", texto_publicado="OFERTA-R",
        estado=PublicacionCarga.ESTADO_ABIERTA, modo_precio=PublicacionCarga.PRECIO_ABIERTO,
    )
    return pub


def _carrier(n):
    c = Transportista.objects.create(nombre=f"T{n}")
    TransportistaVehiculo.objects.create(
        transportista=c, placa=f"RR{n}-100", tipo_vehiculo=TipoVehiculo.objects.get(codigo="camion"),
    )
    return c


class PrecioSugeridoTests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()

    def test_markup_por_defecto_25(self):
        self.assertEqual(precio_cliente_sugerido(800), Decimal("1000"))

    def test_markup_configurable(self):
        cfg = ConfiguracionOperaciones.get_solo()
        cfg.markup_tercerizacion_porcentaje = 40
        cfg.save()
        self.assertEqual(precio_cliente_sugerido(1000), Decimal("1400"))

    def test_sin_costo_es_none(self):
        self.assertIsNone(precio_cliente_sugerido(None))
        self.assertIsNone(precio_cliente_sugerido(0))

    def test_evaluar_margen(self):
        ev = evaluar_margen_tercerizacion(1000, 800)
        self.assertEqual(ev["margin"], 200.0)
        self.assertEqual(ev["pct"], 20.0)
        self.assertTrue(ev["meetsFloor"])  # 1000 >= 800*1.2
        self.assertFalse(evaluar_margen_tercerizacion(900, 800)["meetsFloor"])  # < 960


class AdjudicarFijaPrecioTests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()
        self.user = User.objects.create_user("r_user", password="x")

    def test_servicio_sin_precio_toma_costo_mas_markup(self):
        pub = _pub(1, precio=None)
        o, _ = adj.registrar_oferta(pub, monto=800, usuario=self.user, transportista=_carrier(1))
        adj.adjudicar_publicacion(pub, o, self.user)
        pub.servicio.refresh_from_db()
        self.assertEqual(pub.servicio.precio, Decimal("1000"))  # 800 + 25%

    def test_servicio_con_precio_no_se_pisa(self):
        pub = _pub(2, precio=1500)
        o, _ = adj.registrar_oferta(pub, monto=800, usuario=self.user, transportista=_carrier(2))
        adj.adjudicar_publicacion(pub, o, self.user)
        pub.servicio.refresh_from_db()
        self.assertEqual(pub.servicio.precio, Decimal("1500"))

    def test_precio_cliente_explicito_gana(self):
        pub = _pub(3, precio=None)
        o, _ = adj.registrar_oferta(pub, monto=800, usuario=self.user, transportista=_carrier(3))
        adj.adjudicar_publicacion(pub, o, self.user, precio_cliente=1300)
        pub.servicio.refresh_from_db()
        self.assertEqual(pub.servicio.precio, Decimal("1300"))

    def test_precio_bajo_el_piso_bloquea(self):
        pub = _pub(4, precio=None)
        o, _ = adj.registrar_oferta(pub, monto=800, usuario=self.user, transportista=_carrier(4))
        with self.assertRaises(adj.AdjudicacionError):
            adj.adjudicar_publicacion(pub, o, self.user, precio_cliente=850)  # < 960

    def test_precio_bajo_el_piso_con_autorizacion(self):
        pub = _pub(5, precio=None)
        o, _ = adj.registrar_oferta(pub, monto=800, usuario=self.user, transportista=_carrier(5))
        adj.adjudicar_publicacion(pub, o, self.user, precio_cliente=850, autoriza_bajo_margen=True)
        pub.servicio.refresh_from_db()
        self.assertEqual(pub.servicio.precio, Decimal("850"))


class OutsourcingSettingsMarkupAPITests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()
        Group.objects.get_or_create(name="Despacho")
        self.u = User.objects.create_user("r_despacho", password="x")
        self.u.groups.add(Group.objects.get(name="Despacho"))
        self.client.force_authenticate(self.u)

    def test_get_incluye_markup(self):
        r = self.client.get("/api/v2/outsourcing/settings")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["markupPercent"], 25.0)

    def test_patch_markup(self):
        r = self.client.patch("/api/v2/outsourcing/settings", {"markupPercent": 30}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["markupPercent"], 30.0)
        self.assertEqual(ConfiguracionOperaciones.get_solo().markup_tercerizacion_porcentaje, Decimal("30"))

    def test_patch_markup_fuera_de_rango(self):
        r = self.client.patch("/api/v2/outsourcing/settings", {"markupPercent": 500}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_patch_minimo_comisionable(self):
        r = self.client.patch("/api/v2/outsourcing/settings", {"minCommissionableAmount": 300}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["minCommissionableAmount"], 300.0)
        self.assertEqual(ConfiguracionOperaciones.get_solo().monto_minimo_comisionable, Decimal("300"))


def _tramos_base():
    TramoComision.objects.bulk_create([
        TramoComision(categoria="", monto_desde=0, monto_hasta=1000, porcentaje=25),
        TramoComision(categoria="", monto_desde=1000, monto_hasta=5000, porcentaje=18),
        TramoComision(categoria="", monto_desde=5000, monto_hasta=None, porcentaje=10),
        TramoComision(categoria="mudanza", monto_desde=0, monto_hasta=None, porcentaje=30),
    ])


class TablaComisionTests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()
        TramoComision.objects.all().delete()

    def test_sin_tabla_cae_al_markup(self):
        # markup 25 → comisión equivalente 25/125 = 20 %
        self.assertEqual(comision_pct(500), Decimal("20.00"))

    def test_tramo_por_monto(self):
        _tramos_base()
        self.assertEqual(comision_pct(500), Decimal("25"))
        self.assertEqual(comision_pct(2000), Decimal("18"))
        self.assertEqual(comision_pct(9000), Decimal("10"))

    def test_categoria_pisa_a_general(self):
        _tramos_base()
        self.assertEqual(comision_pct(2000, "mudanza"), Decimal("30"))
        self.assertEqual(comision_pct(2000, "cajas"), Decimal("18"))  # sin tabla propia → general

    def test_precio_sugerido_usa_la_tabla(self):
        _tramos_base()
        # costo 800 → tramo 25 % → 800 / 0.75 = 1067 → re-cae en tramo 18 % (>1000)
        # → 800 / 0.82 = 976 → vuelve a 25 %... converge cerca del borde
        p = precio_cliente_sugerido(800)
        self.assertGreater(p, Decimal("900"))
        self.assertLess(p, Decimal("1100"))

    def test_desglose(self):
        _tramos_base()
        d = desglose_comision(2000, 1600, "")
        self.assertEqual(d["commissionPct"], 18.0)
        self.assertEqual(d["commission"], 360.0)
        self.assertEqual(d["carrierPayout"], 1640.0)

    def test_seed_idempotente(self):
        from django.core.management import call_command
        call_command("seed_comisiones")
        n = TramoComision.objects.count()
        self.assertGreater(n, 0)
        call_command("seed_comisiones")
        self.assertEqual(TramoComision.objects.count(), n)


class CommissionTiersAPITests(APITestCase):
    def setUp(self):
        TramoComision.objects.all().delete()
        for g in ("Gerencia", "Despacho"):
            Group.objects.get_or_create(name=g)
        self.gerente = User.objects.create_user("c_ger", password="x")
        self.gerente.groups.add(Group.objects.get(name="Gerencia"))
        self.despacho = User.objects.create_user("c_desp", password="x")
        self.despacho.groups.add(Group.objects.get(name="Despacho"))

    def test_despacho_no_puede(self):
        self.client.force_authenticate(self.despacho)
        self.assertEqual(self.client.get("/api/v2/outsourcing/commission-tiers").status_code, 403)

    def test_crud(self):
        self.client.force_authenticate(self.gerente)
        r = self.client.post("/api/v2/outsourcing/commission-tiers",
                             {"category": "mudanza", "from": 0, "to": 2000, "percent": 28}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        tid = r.data["id"]
        r = self.client.patch(f"/api/v2/outsourcing/commission-tiers/{tid}", {"percent": 26}, format="json")
        self.assertEqual(r.data["percent"], 26.0)
        r = self.client.get("/api/v2/outsourcing/commission-tiers")
        self.assertEqual(len(r.data["tiers"]), 1)
        self.assertTrue(any(c["value"] == "mudanza" for c in r.data["categories"]))
        self.assertEqual(self.client.delete(f"/api/v2/outsourcing/commission-tiers/{tid}").status_code, 204)

    def test_rechaza_rango_invalido(self):
        self.client.force_authenticate(self.gerente)
        r = self.client.post("/api/v2/outsourcing/commission-tiers",
                             {"category": "", "from": 5000, "to": 1000, "percent": 10}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_rechaza_categoria_invalida(self):
        self.client.force_authenticate(self.gerente)
        r = self.client.post("/api/v2/outsourcing/commission-tiers",
                             {"category": "inexistente", "from": 0, "percent": 10}, format="json")
        self.assertEqual(r.status_code, 400)
