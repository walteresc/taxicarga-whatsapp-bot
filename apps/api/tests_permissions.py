"""Gerencia como superadministrador (decisión del usuario, 2026-09-12):
pasa cualquier `HasAnyRole`, aunque esa vista no la liste explícitamente, y
`role_names()` la refleja como si tuviera 'Administrador' (para que el menú
del front la trate igual)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.api.permissions import role_names

User = get_user_model()


class GerenciaSuperadminTests(APITestCase):
    def setUp(self):
        self.gerente = User.objects.create_user("ger_test", password="x")
        self.gerente.groups.add(Group.objects.get_or_create(name="Gerencia")[0])

    def test_pasa_una_vista_que_no_lista_gerencia_explicitamente(self):
        # /api/v2/vehicle-types/ solo lista Administrador/Supervisor a propósito
        # (es también la fuente del combo de tipos de vehículo en Tercerización) —
        # Gerencia debe entrar igual, por el bypass, no porque esté en esa lista.
        self.client.force_login(self.gerente)
        r = self.client.get("/api/v2/vehicle-types/")
        self.assertEqual(r.status_code, 200, r.content)

    def test_role_names_le_agrega_administrador(self):
        self.assertIn("Administrador", role_names(self.gerente))

    def test_otro_rol_sin_gerencia_no_tiene_el_bypass(self):
        u = User.objects.create_user("desp_test", password="x")
        u.groups.add(Group.objects.get_or_create(name="Despacho")[0])
        self.client.force_login(u)
        # Despacho no está en _ROLES de vehicle-types (Administrador/Supervisor) →
        # sin el bypass de Gerencia, debe seguir sin entrar.
        r = self.client.get("/api/v2/vehicle-types/")
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("Administrador", role_names(u))
