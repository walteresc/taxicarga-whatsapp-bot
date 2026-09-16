"""F7 · Cotización rápida de invitado + conversión a cliente/empresa."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import caches
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente, ClienteUsuario
from apps.leads.models import Lead

User = get_user_model()

_QUOTE = {
    "origin": {"district": "Miraflores", "address": "Av Larco 100"},
    "destination": {"district": "Surco", "address": "Av Primavera 500"},
    "cargo": {"category": "mudanza", "detail": "1 amb"},
    "date": "2026-11-01",
    "contact": {"phone": "+51900111222", "name": "Invitada Uno"},
}

# Rates altas para no chocar con el throttle dentro de un test.
_NO_THROTTLE = override_settings(REST_FRAMEWORK={
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_RATES": {
        "guest_quote": "1000/hour", "guest_quote_preview": "1000/hour", "guest_signup": "1000/hour",
    },
})


@_NO_THROTTLE
class GuestQuoteTests(APITestCase):
    def setUp(self):
        caches["throttle"].clear()

    def test_cotiza_sin_login_y_crea_lead_invitado(self):
        r = self.client.post("/api/v2/guest/quote", _QUOTE, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["quoteCode"].startswith("CRG-"))
        lead = Lead.objects.get(codigo=r.data["quoteCode"])
        self.assertEqual(lead.origen_carga, "invitado")
        self.assertEqual(lead.cliente.telefono, "+51900111222")
        self.assertEqual(lead.ubicaciones.count(), 2)

    def test_coordenadas_lejanas_marcan_interprovincial(self):
        # Piura está a ~900 km de Lima Cercado (radio local default 60 km).
        payload = {
            **_QUOTE,
            "origin": {"district": "Lima", "address": "Jr Union 100", "lat": -12.0464, "lng": -77.0428},
            "destination": {"district": "Piura", "address": "Av Grau 200", "lat": -5.1945, "lng": -80.6328},
        }
        r = self.client.post("/api/v2/guest/quote", payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        lead = Lead.objects.get(codigo=r.data["quoteCode"])
        self.assertTrue(lead.es_interprovincial)
        self.assertEqual(float(lead.lat_destino), -5.1945)

    def test_coordenadas_cercanas_no_marcan_interprovincial(self):
        payload = {
            **_QUOTE,
            "origin": {"district": "Miraflores", "address": "Av Larco 100", "lat": -12.1211, "lng": -77.0297},
            "destination": {"district": "Surco", "address": "Av Primavera 500", "lat": -12.1350, "lng": -76.9900},
        }
        r = self.client.post("/api/v2/guest/quote", payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        lead = Lead.objects.get(codigo=r.data["quoteCode"])
        self.assertFalse(lead.es_interprovincial)

    def test_honeypot_no_crea_nada(self):
        n = Lead.objects.count()
        r = self.client.post("/api/v2/guest/quote", {**_QUOTE, "website": "http://spam"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data["quoteCode"])
        self.assertEqual(Lead.objects.count(), n)

    def test_falta_telefono_400(self):
        payload = {**_QUOTE, "contact": {"name": "x"}}
        r = self.client.post("/api/v2/guest/quote", payload, format="json")
        self.assertEqual(r.status_code, 400)

    def test_con_paradas_guarda_la_ruta_completa_y_pasa_a_asesor(self):
        payload = {
            **_QUOTE,
            "stops": [{"district": "San Borja"}, {"district": ""}],   # el vacío se descarta
        }
        r = self.client.post("/api/v2/guest/quote", payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        lead = Lead.objects.get(codigo=r.data["quoteCode"])
        self.assertEqual(list(lead.ubicaciones.order_by("orden").values_list("tipo", "distrito")), [
            ("origen", "Miraflores"), ("parada", "San Borja"), ("destino", "Surco"),
        ])
        self.assertEqual(r.data["price"]["mode"], "advisor")


@_NO_THROTTLE
class PreviewQuoteTests(APITestCase):
    """No persiste nada — ni Cliente ni Lead — a diferencia de /guest/quote."""
    def setUp(self):
        caches["throttle"].clear()

    def _post(self, **overrides):
        payload = {
            "origin": {"district": "Lima", "lat": -12.0464, "lng": -77.0428},
            "destination": {"district": "Trujillo", "lat": -8.1116, "lng": -79.0288},
            "cargo": {"category": "cajas", "weightKg": "100"},
            **overrides,
        }
        return self.client.post("/api/v2/guest/quote/preview", payload, format="json")

    def test_no_crea_lead_ni_cliente(self):
        n_leads, n_clientes = Lead.objects.count(), Cliente.objects.count()
        r = self._post()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Lead.objects.count(), n_leads)
        self.assertEqual(Cliente.objects.count(), n_clientes)

    def test_ruta_local_no_ofrece_consolidada(self):
        r = self._post(
            origin={"district": "Miraflores", "lat": -12.1211, "lng": -77.0297},
            destination={"district": "Surco", "lat": -12.1350, "lng": -76.9900},
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.data["isInterprovincial"])
        self.assertIsNone(r.data["consolidated"])
        self.assertIsNotNone(r.data["express"])

    def test_ruta_interprovincial_frecuente_ofrece_ambas(self):
        from apps.tercerizacion.models import TarifaCargaParcial
        TarifaCargaParcial.objects.create(
            destino="trujillo", peso_desde_kg=0, peso_hasta_kg=None,
            precio_por_kg="3.50", monto_minimo="35", dias_estimados=3, activo=True,
        )
        r = self._post()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["isInterprovincial"])
        self.assertIsNotNone(r.data["consolidated"])
        self.assertEqual(r.data["consolidated"]["mode"], "auto")

    def test_ruta_interprovincial_no_frecuente_no_ofrece_consolidada(self):
        # Yauyos no tiene tarifa propia. Aunque exista una tarifa general
        # ("") que cubriría cualquier destino, a propósito NO cuenta como
        # "ruta frecuente" — por eso no se ofrece Consolidada.
        from apps.tercerizacion.models import TarifaCargaParcial
        TarifaCargaParcial.objects.create(
            destino="", peso_desde_kg=0, peso_hasta_kg=None,
            precio_por_kg="4.00", monto_minimo="40", dias_estimados=5, activo=True,
        )
        r = self._post(
            destination={"district": "Yauyos", "lat": -12.4708, "lng": -75.9083},
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["isInterprovincial"])
        self.assertIsNone(r.data["consolidated"])

    def test_falta_distrito_400(self):
        r = self._post(destination={})
        self.assertEqual(r.status_code, 400)


@_NO_THROTTLE
class GuestSignupTests(APITestCase):
    def setUp(self):
        caches["throttle"].clear()
        Group.objects.get_or_create(name="Cliente Portal")

    def test_alta_de_cuenta_loguea_y_enlaza_la_cotizacion(self):
        code = self.client.post("/api/v2/guest/quote", _QUOTE, format="json").data["quoteCode"]
        r = self.client.post("/api/v2/guest/signup", {
            "quoteCode": code, "phone": "+51900111222", "name": "Invitada Uno",
            "password": "unaClaveSegura", "email": "inv@x.com",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNotNone(r.data["user"]["portalCustomerId"])

        cu = ClienteUsuario.objects.get(usuario__username="51900111222")
        self.assertEqual(cu.cliente.tipo, Cliente.TIPO_FRECUENTE)
        Lead.objects.get(codigo=code, origen_carga="portal_cliente")

        # queda logueado (sesión) → puede pedir sus cargas
        self.assertEqual(self.client.get("/api/v2/portal/customer/loads").status_code, 200)

    def test_empresa_crea_empresa_y_marca_tipo(self):
        r = self.client.post("/api/v2/guest/signup", {
            "phone": "+51900333444", "name": "Juan Empresa", "password": "otraClave123",
            "isCompany": True, "ruc": "20123456789", "razonSocial": "Carga SAC",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        cu = ClienteUsuario.objects.get(usuario__username="51900333444")
        self.assertEqual(cu.cliente.tipo, Cliente.TIPO_EMPRESA)
        self.assertEqual(cu.empresa.razon_social, "Carga SAC")

    def test_telefono_con_cuenta_activa_es_rechazado(self):
        c = Cliente.objects.create(telefono="+51900555666", nombre="Ya Tiene")
        u = User.objects.create_user("900555666", password="x")
        ClienteUsuario.objects.create(usuario=u, cliente=c)
        r = self.client.post("/api/v2/guest/signup", {
            "phone": "+51900555666", "name": "Intruso", "password": "claveNueva1",
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_telefono_sin_cuenta_se_adjunta(self):
        Cliente.objects.create(telefono="+51900777888", nombre="Bot Lo Creo")
        r = self.client.post("/api/v2/guest/signup", {
            "phone": "+51900777888", "name": "Bot Lo Creo", "password": "claveNueva1",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(ClienteUsuario.objects.filter(cliente__telefono="+51900777888").exists())

    def test_password_corta_400(self):
        r = self.client.post("/api/v2/guest/signup", {
            "phone": "+51900999000", "name": "x", "password": "corta",
        }, format="json")
        self.assertEqual(r.status_code, 400)
