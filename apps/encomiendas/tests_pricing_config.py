"""API v2 de configuración de Encomiendas: /api/v2/shipments/pricing-config."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.encomiendas.models import ConfiguracionEncomiendas

User = get_user_model()


class _Authed(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("enc_pricing_user", password="x")
        g, _ = Group.objects.get_or_create(name="Finanzas")
        self.user.groups.add(g)
        self.client.force_login(self.user)


class EncomiendasPricingConfigGetTests(_Authed):
    def test_sin_config_previa_crea_una_con_defaults_originales(self):
        self.assertEqual(ConfiguracionEncomiendas.objects.count(), 0)
        r = self.client.get("/api/v2/shipments/pricing-config")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(ConfiguracionEncomiendas.objects.count(), 1)
        self.assertEqual(r.data["comision_cod_porcentaje"], 3.0)
        self.assertEqual(r.data["costo_recojo_domicilio_nacional"], 0.0)
        self.assertEqual(r.data["costo_entrega_domicilio_nacional"], 0.0)
        self.assertTrue(r.data["envioIncluidoEnCod"])


class EncomiendasPricingConfigPatchTests(_Authed):
    def test_cambiar_costos_de_recojo_y_entrega(self):
        r = self.client.patch("/api/v2/shipments/pricing-config", {
            "costo_recojo_domicilio_nacional": 12, "costo_entrega_domicilio_nacional": 8,
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["costo_recojo_domicilio_nacional"], 12.0)
        self.assertEqual(r.data["costo_entrega_domicilio_nacional"], 8.0)

    def test_valor_negativo_400(self):
        r = self.client.patch(
            "/api/v2/shipments/pricing-config", {"costo_recojo_domicilio_nacional": -5}, format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_cambia_envio_incluido_en_cod(self):
        r = self.client.patch("/api/v2/shipments/pricing-config", {"envioIncluidoEnCod": False}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data["envioIncluidoEnCod"])


class EncomiendasPricingConfigRbacTests(APITestCase):
    def test_sin_rol_no_puede_ver(self):
        user = User.objects.create_user("sin_rol_enc_precios", password="x")
        self.client.force_login(user)
        r = self.client.get("/api/v2/shipments/pricing-config")
        self.assertEqual(r.status_code, 403)

    def test_supervisor_no_entra(self):
        user = User.objects.create_user("sup_enc_precios", password="x")
        g, _ = Group.objects.get_or_create(name="Supervisor")
        user.groups.add(g)
        self.client.force_login(user)
        r = self.client.get("/api/v2/shipments/pricing-config")
        self.assertEqual(r.status_code, 403)
