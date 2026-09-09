"""F4 · API de usuarios y permisos."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

User = get_user_model()


class UsersApiTests(APITestCase):
    def setUp(self):
        for n in ["Administrador", "Admin de sistema", "Asesor de Ventas", "Gerencia"]:
            Group.objects.get_or_create(name=n)
        self.admin = User.objects.create_user("sys", password="x")
        self.admin.groups.add(Group.objects.get(name="Admin de sistema"))
        self.other = User.objects.create_user("vendedor", password="x", first_name="Ana")
        self.other.groups.add(Group.objects.get(name="Asesor de Ventas"))

    def test_asesor_no_entra(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/api/v2/users/").status_code, 403)

    def test_admin_de_sistema_lista_y_cambia_roles(self):
        self.client.force_login(self.admin)
        r = self.client.get("/api/v2/users/")
        self.assertEqual(r.status_code, 200)

        r = self.client.get("/api/v2/roles/")
        self.assertTrue(any(x["name"] == "Despacho" for x in r.data))

        r = self.client.patch(f"/api/v2/users/{self.other.id}/",
                              {"roles": ["Asesor de Ventas", "Gerencia"]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(sorted(r.data["roles"]), ["Asesor de Ventas", "Gerencia"])

    def test_rol_invalido_rechazado(self):
        self.client.force_login(self.admin)
        r = self.client.patch(f"/api/v2/users/{self.other.id}/",
                              {"roles": ["Jefe Supremo"]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_no_puede_quitarse_su_propio_rol_de_admin(self):
        self.client.force_login(self.admin)
        r = self.client.patch(f"/api/v2/users/{self.admin.id}/",
                              {"roles": ["Asesor de Ventas"]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_no_puede_desactivarse_a_si_mismo(self):
        self.client.force_login(self.admin)
        r = self.client.patch(f"/api/v2/users/{self.admin.id}/", {"active": False}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_alta_de_usuario_con_rol(self):
        self.client.force_login(self.admin)
        r = self.client.post("/api/v2/users/", {
            "username": "nuevo_asesor", "password": "ClaveSegura123",
            "fullName": "Ana Torres", "email": "ana@x.com",
            "roles": ["Asesor de Ventas"],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        u = User.objects.get(username="nuevo_asesor")
        self.assertFalse(u.is_staff)
        self.assertFalse(u.is_superuser)
        self.assertTrue(u.check_password("ClaveSegura123"))
        self.assertEqual(list(u.groups.values_list("name", flat=True)), ["Asesor de Ventas"])
        self.assertEqual(u.first_name, "Ana")
        self.assertEqual(u.last_name, "Torres")

    def test_alta_username_duplicado_400(self):
        self.client.force_login(self.admin)
        r = self.client.post("/api/v2/users/", {
            "username": "vendedor", "password": "ClaveSegura123",
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_alta_password_debil_400(self):
        self.client.force_login(self.admin)
        r = self.client.post("/api/v2/users/", {"username": "x1", "password": "123"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_asesor_no_puede_crear_usuarios(self):
        self.client.force_login(self.other)
        r = self.client.post("/api/v2/users/", {"username": "y1", "password": "ClaveSegura123"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_reset_password_via_patch(self):
        self.client.force_login(self.admin)
        r = self.client.patch(f"/api/v2/users/{self.other.id}/", {"password": "OtraClave456"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.other.refresh_from_db()
        self.assertTrue(self.other.check_password("OtraClave456"))
