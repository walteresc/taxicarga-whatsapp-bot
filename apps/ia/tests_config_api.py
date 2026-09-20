"""API v2 de configuración de IA: /api/v2/ia/config — elegir proveedor/modelo
por propósito desde el panel, sin tocar la API key (siempre en .env)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.ia.models import ConfiguracionIA
from apps.ia.providers import provider_name_for

User = get_user_model()


class _Authed(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("ia_config_user", password="x")
        g, _ = Group.objects.get_or_create(name="Admin de sistema")
        self.user.groups.add(g)
        self.client.force_login(self.user)


class AIConfigGetTests(_Authed):
    def test_sin_config_previa_crea_una_con_defaults_vacios(self):
        self.assertEqual(ConfiguracionIA.objects.count(), 0)
        r = self.client.get("/api/v2/ia/config")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(ConfiguracionIA.objects.count(), 1)
        self.assertEqual(r.data["defaultProvider"], "")
        self.assertEqual(r.data["extractionProvider"], "")

    def test_incluye_effective_resuelto_por_settings_sin_override(self):
        r = self.client.get("/api/v2/ia/config")
        self.assertEqual(r.data["effective"]["extraction"], "openai")

    def test_incluye_flags_de_key_configurada(self):
        r = self.client.get("/api/v2/ia/config")
        self.assertIn("hasOpenaiKey", r.data)
        self.assertIn("hasDeepseekKey", r.data)


class AIConfigPatchTests(_Authed):
    def test_cambiar_proveedor_de_extraccion(self):
        r = self.client.patch("/api/v2/ia/config", {"extractionProvider": "deepseek"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["extractionProvider"], "deepseek")
        self.assertEqual(r.data["effective"]["extraction"], "deepseek")
        # No toca los otros propósitos.
        self.assertEqual(r.data["conversationProvider"], "")

    def test_volver_a_vacio_restaura_el_default_del_servidor(self):
        ConfiguracionIA.objects.create(pk=1, proveedor_extraccion="deepseek")
        r = self.client.patch("/api/v2/ia/config", {"extractionProvider": ""}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["effective"]["extraction"], "openai")

    def test_proveedor_default_aplica_a_los_que_no_tienen_override(self):
        r = self.client.patch("/api/v2/ia/config", {"defaultProvider": "deepseek"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["effective"]["extraction"], "deepseek")
        self.assertEqual(r.data["effective"]["conversation"], "deepseek")

    def test_proveedor_invalido_400(self):
        r = self.client.patch("/api/v2/ia/config", {"extractionProvider": "gemini"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cambiar_modelo_openai(self):
        r = self.client.patch("/api/v2/ia/config", {"openaiModel": "gpt-4.1"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["openaiModel"], "gpt-4.1")

    def test_no_expone_ni_acepta_api_key(self):
        r = self.client.patch("/api/v2/ia/config", {"apiKey": "sk-lo-que-sea"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertNotIn("apiKey", r.data)
        self.assertNotIn("openaiApiKey", r.data)


class AIConfigRbacTests(APITestCase):
    def test_sin_rol_no_puede_ver(self):
        user = User.objects.create_user("sin_rol_ia", password="x")
        self.client.force_login(user)
        r = self.client.get("/api/v2/ia/config")
        self.assertEqual(r.status_code, 403)

    def test_supervisor_no_entra(self):
        user = User.objects.create_user("sup_ia", password="x")
        g, _ = Group.objects.get_or_create(name="Supervisor")
        user.groups.add(g)
        self.client.force_login(user)
        r = self.client.get("/api/v2/ia/config")
        self.assertEqual(r.status_code, 403)


class ProviderNameForConfigTests(APITestCase):
    """`provider_name_for` es lo que usa `build_provider` en todo el
    proyecto — confirma que el override de ConfiguracionIA realmente se
    respeta ahí, no solo en el payload del endpoint."""

    def test_sin_config_usa_settings(self):
        self.assertEqual(provider_name_for("extraction"), "openai")

    def test_override_puntual_gana_sobre_el_default_general(self):
        ConfiguracionIA.objects.create(pk=1, proveedor_default="deepseek", proveedor_extraccion="openai")
        self.assertEqual(provider_name_for("extraction"), "openai")
        self.assertEqual(provider_name_for("conversation"), "deepseek")
