"""API v2 de configuración de precios: /api/v2/cotizador/pricing-config —
parámetros del cálculo por reglas base, editables desde el panel."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente
from apps.cotizador.models import ConfiguracionPrecios
from apps.cotizador.pricing import fallback_price_for_lead
from apps.leads.models import Lead

User = get_user_model()


class _Authed(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("pricing_config_user", password="x")
        g, _ = Group.objects.get_or_create(name="Finanzas")
        self.user.groups.add(g)
        self.client.force_login(self.user)


class PricingConfigGetTests(_Authed):
    def test_sin_config_previa_crea_una_con_defaults_originales(self):
        self.assertEqual(ConfiguracionPrecios.objects.count(), 0)
        r = self.client.get("/api/v2/cotizador/pricing-config")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(ConfiguracionPrecios.objects.count(), 1)
        self.assertEqual(r.data["base_carga"], 180.0)
        self.assertEqual(r.data["costo_por_kg"], 0.12)

    def test_incluye_todos_los_parametros(self):
        r = self.client.get("/api/v2/cotizador/pricing-config")
        for campo in [
            "base_mudanza", "base_carga", "base_traslado_pequeno", "base_oficina", "base_corporativo",
            "costo_por_kg", "costo_por_m3", "costo_por_piso_sin_ascensor", "km_gratis", "costo_por_km",
            "rango_min_pct", "rango_max_pct",
        ]:
            self.assertIn(campo, r.data)


class PricingConfigPatchTests(_Authed):
    def test_cambiar_precio_base_de_carga(self):
        r = self.client.patch("/api/v2/cotizador/pricing-config", {"base_carga": 250}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["base_carga"], 250.0)
        # No toca otros campos.
        self.assertEqual(r.data["base_mudanza"], 150.0)

    def test_valor_negativo_400(self):
        r = self.client.patch("/api/v2/cotizador/pricing-config", {"base_carga": -10}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_valor_no_numerico_400(self):
        r = self.client.patch("/api/v2/cotizador/pricing-config", {"base_carga": "abc"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_el_cambio_se_refleja_en_el_calculo_real(self):
        self.client.patch("/api/v2/cotizador/pricing-config", {"base_carga": "999.00"}, format="json")
        cliente = Cliente.objects.create(telefono="51955555501")
        lead = Lead.objects.create(cliente=cliente, tipo_servicio="carga", distrito_origen="A", distrito_destino="B")
        _min, _max, recommended = fallback_price_for_lead(lead)
        self.assertEqual(recommended, Decimal("999.00"))


class PricingConfigRbacTests(APITestCase):
    def test_sin_rol_no_puede_ver(self):
        user = User.objects.create_user("sin_rol_precios", password="x")
        self.client.force_login(user)
        r = self.client.get("/api/v2/cotizador/pricing-config")
        self.assertEqual(r.status_code, 403)

    def test_supervisor_no_entra(self):
        """Configuración → Precios usa el mismo criterio que Comisiones de
        tercerización (Administrador/Gerencia/Finanzas) — a propósito sin
        Supervisor ni Asesor de Ventas."""
        user = User.objects.create_user("sup_precios", password="x")
        g, _ = Group.objects.get_or_create(name="Supervisor")
        user.groups.add(g)
        self.client.force_login(user)
        r = self.client.get("/api/v2/cotizador/pricing-config")
        self.assertEqual(r.status_code, 403)

    def test_gerencia_entra_por_el_bypass(self):
        user = User.objects.create_user("ger_precios", password="x")
        g, _ = Group.objects.get_or_create(name="Gerencia")
        user.groups.add(g)
        self.client.force_login(user)
        r = self.client.get("/api/v2/cotizador/pricing-config")
        self.assertEqual(r.status_code, 200, r.data)
