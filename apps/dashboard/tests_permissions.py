from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.urls import reverse


class PermissionsTests(TestCase):
    def setUp(self):
        roles = ["Administrador", "Supervisor", "Asesor de Ventas", "Conductor", "Ayudante"]
        for role in roles:
            Group.objects.get_or_create(name=role)

        self.admin_user = User.objects.create_user("admin", password="test123")
        admin_group = Group.objects.get(name="Administrador")
        self.admin_user.groups.add(admin_group)

        self.supervisor_user = User.objects.create_user("supervisor", password="test123")
        supervisor_group = Group.objects.get(name="Supervisor")
        self.supervisor_user.groups.add(supervisor_group)

        self.asesor_user = User.objects.create_user("asesor", password="test123")
        asesor_group = Group.objects.get(name="Asesor de Ventas")
        self.asesor_user.groups.add(asesor_group)

        self.conductor_user = User.objects.create_user("conductor", password="test123")
        conductor_group = Group.objects.get(name="Conductor")
        self.conductor_user.groups.add(conductor_group)

        self.ayudante_user = User.objects.create_user("ayudante", password="test123")
        ayudante_group = Group.objects.get(name="Ayudante")
        self.ayudante_user.groups.add(ayudante_group)

    def test_administrador_access_campo_and_pizarra(self):
        self.client.login(username="admin", password="test123")
        response = self.client.get(reverse("dashboard-campo"))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertEqual(response.status_code, 200)

    def test_supervisor_access_campo_and_pizarra(self):
        self.client.login(username="supervisor", password="test123")
        response = self.client.get(reverse("dashboard-campo"))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertEqual(response.status_code, 200)

    def test_asesor_access_campo_and_pizarra(self):
        self.client.login(username="asesor", password="test123")
        response = self.client.get(reverse("dashboard-campo"))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertEqual(response.status_code, 200)

    def test_conductor_no_access_to_campo(self):
        self.client.login(username="conductor", password="test123")
        response = self.client.get(reverse("dashboard-campo"))
        self.assertEqual(response.status_code, 302)

    def test_ayudante_no_access_to_campo(self):
        self.client.login(username="ayudante", password="test123")
        response = self.client.get(reverse("dashboard-campo"))
        self.assertEqual(response.status_code, 302)

