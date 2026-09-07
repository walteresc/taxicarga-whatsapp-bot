"""RBAC de pausar/activar/consultar el bot de clientes globalmente
(apps/whatsapp_bot_v4/api_conversation_control.py). Antes cualquier usuario
autenticado podía pausar el bot para TODAS las conversaciones sin tener
ningún rol comercial — se restringe a Administrador/Supervisor/Asesor de
Ventas, igual que el resto del pipeline comercial."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.whatsapp_bot_v4.models import BotGlobalConfig

User = get_user_model()


class _WithRole(APITestCase):
    role = "Supervisor"

    def setUp(self):
        self.user = User.objects.create_user("control_user", password="x")
        g, _ = Group.objects.get_or_create(name=self.role)
        self.user.groups.add(g)
        self.client.force_login(self.user)


class BotControlRoleAllowedTests(_WithRole):
    def test_pause_global(self):
        r = self.client.post("/webhooks/api/control/pause-global/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(BotGlobalConfig.objects.first().is_paused)

    def test_activate_global(self):
        BotGlobalConfig.objects.create(is_paused=True)
        r = self.client.post("/webhooks/api/control/activate-global/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(BotGlobalConfig.objects.first().is_paused)

    def test_bot_status(self):
        r = self.client.get("/webhooks/api/control/bot-status/")
        self.assertEqual(r.status_code, 200, r.data)


class BotControlRoleDeniedTests(APITestCase):
    def test_sin_rol_no_puede_pausar(self):
        user = User.objects.create_user("sin_rol", password="x")
        self.client.force_login(user)
        r = self.client.post("/webhooks/api/control/pause-global/")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(BotGlobalConfig.objects.exists())

    def test_sin_rol_no_puede_activar(self):
        user = User.objects.create_user("sin_rol2", password="x")
        self.client.force_login(user)
        r = self.client.post("/webhooks/api/control/activate-global/")
        self.assertEqual(r.status_code, 403)

    def test_sin_rol_no_puede_ver_estado(self):
        user = User.objects.create_user("sin_rol3", password="x")
        self.client.force_login(user)
        r = self.client.get("/webhooks/api/control/bot-status/")
        self.assertEqual(r.status_code, 403)

    def test_anonimo_no_puede_pausar(self):
        r = self.client.post("/webhooks/api/control/pause-global/")
        self.assertEqual(r.status_code, 403)
