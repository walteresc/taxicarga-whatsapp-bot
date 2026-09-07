"""API v2 de configuración del bot: /api/v2/bot/status, /operations/pause,
/operations/resume. Solo el interruptor 'operations' escribe desde aquí —
customers/carriers son de solo lectura (las escrituras siguen viviendo en los
endpoints ya existentes, ver apps/whatsapp_bot_v4/api/views.py)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.whatsapp_bot_v4.models import BotGlobalConfig

User = get_user_model()


class _Authed(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("bot_config_user", password="x")
        g, _ = Group.objects.get_or_create(name="Supervisor")
        self.user.groups.add(g)
        self.client.force_login(self.user)


class BotStatusApiTests(_Authed):
    def test_estado_sin_config_previa_crea_una_con_defaults(self):
        self.assertEqual(BotGlobalConfig.objects.count(), 0)
        r = self.client.get("/api/v2/bot/status")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(BotGlobalConfig.objects.count(), 1)
        self.assertFalse(r.data["customers"]["paused"])
        self.assertTrue(r.data["carriers"]["paused"])  # default True
        self.assertFalse(r.data["operations"]["paused"])

    def test_estado_refleja_config_existente(self):
        BotGlobalConfig.objects.create(
            is_paused=True, transportistas_paused=False, operativo_paused=True,
        )
        r = self.client.get("/api/v2/bot/status")
        self.assertTrue(r.data["customers"]["paused"])
        self.assertFalse(r.data["carriers"]["paused"])
        self.assertTrue(r.data["operations"]["paused"])

    def test_carriers_incluye_flag_de_despliegue(self):
        r = self.client.get("/api/v2/bot/status")
        self.assertIn("enabledInDeployment", r.data["carriers"])


class BotOperationsToggleApiTests(_Authed):
    def test_pausar_operativo(self):
        r = self.client.post("/api/v2/bot/operations/pause")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["operations"]["paused"])
        self.assertIsNotNone(r.data["operations"]["pausedAt"])
        config = BotGlobalConfig.objects.first()
        self.assertTrue(config.operativo_paused)
        self.assertIsNotNone(config.operativo_paused_at)

    def test_reanudar_operativo(self):
        BotGlobalConfig.objects.create(operativo_paused=True)
        r = self.client.post("/api/v2/bot/operations/resume")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data["operations"]["paused"])
        self.assertIsNone(r.data["operations"]["pausedAt"])

    def test_no_toca_customers_ni_carriers(self):
        BotGlobalConfig.objects.create(is_paused=True, transportistas_paused=False)
        self.client.post("/api/v2/bot/operations/pause")
        config = BotGlobalConfig.objects.first()
        self.assertTrue(config.is_paused)
        self.assertFalse(config.transportistas_paused)


class BotConfigRbacTests(APITestCase):
    def test_sin_rol_no_puede_ver_estado(self):
        user = User.objects.create_user("sin_rol", password="x")
        self.client.force_login(user)
        r = self.client.get("/api/v2/bot/status")
        self.assertEqual(r.status_code, 403)

    def test_sin_autenticar_no_puede_ver_estado(self):
        r = self.client.get("/api/v2/bot/status")
        self.assertEqual(r.status_code, 403)
