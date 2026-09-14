"""Mi perfil (autoservicio): GET/PATCH /api/v2/me, POST /api/v2/me/change-password."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

User = get_user_model()


class MeApiTests(APITestCase):
    def setUp(self):
        Group.objects.get_or_create(name="Despacho")
        self.user = User.objects.create_user(
            "despacho1", password="Clave-Actual1", email="d1@lima.pe", first_name="Diego",
        )
        self.user.groups.add(Group.objects.get(name="Despacho"))
        self.client.force_login(self.user)

    def test_sin_login_no_entra(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/v2/me").status_code, 403)

    def test_ve_sus_datos(self):
        r = self.client.get("/api/v2/me")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["username"], "despacho1")
        self.assertEqual(r.data["roles"], ["Despacho"])
        self.assertIn("dateJoined", r.data)

    def test_edita_nombre_y_email(self):
        r = self.client.patch("/api/v2/me", {"fullName": "Diego Ramos", "email": "nuevo@lima.pe"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["fullName"], "Diego Ramos")
        self.assertEqual(r.data["email"], "nuevo@lima.pe")

    def test_no_puede_tocar_roles_ni_username_desde_aca(self):
        r = self.client.patch("/api/v2/me", {"roles": ["Administrador"], "username": "otro"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "despacho1")
        self.assertEqual(list(self.user.groups.values_list("name", flat=True)), ["Despacho"])


class ChangePasswordApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("despacho2", password="Clave-Actual1")
        self.client.force_login(self.user)

    def test_cambia_contrasena_y_mantiene_la_sesion(self):
        r = self.client.post("/api/v2/me/change-password", {
            "currentPassword": "Clave-Actual1", "newPassword": "Otra-Clave-Nueva9",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        # La sesión sigue viva (update_session_auth_hash) — no pide login de nuevo.
        self.assertEqual(self.client.get("/api/v2/me").status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Otra-Clave-Nueva9"))

    def test_contrasena_actual_incorrecta_rechazada(self):
        r = self.client.post("/api/v2/me/change-password", {
            "currentPassword": "no-es-esta", "newPassword": "Otra-Clave-Nueva9",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("currentPassword", r.data["fields"])

    def test_contrasena_nueva_debil_rechazada(self):
        r = self.client.post("/api/v2/me/change-password", {
            "currentPassword": "Clave-Actual1", "newPassword": "123",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("newPassword", r.data["fields"])
