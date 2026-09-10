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
from apps.tercerizacion.models import PublicacionCarga, Transportista, TransportistaVehiculo
from apps.tercerizacion.services import (
    evaluar_margen_tercerizacion, precio_cliente_sugerido,
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
