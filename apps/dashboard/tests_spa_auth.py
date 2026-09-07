"""El shell de la SPA (index.html) solo se entrega a usuarios autenticados.

Antes, `spa_fallback` servía index.html a cualquiera. Ahora exige sesión y
redirige a /login (conservando ?next=) a los anónimos, salvo en las rutas
públicas (login / registro).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class SpaShellAuthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("spa_user", password="x")

    def test_anonimo_en_ruta_spa_redirige_a_login_con_next(self):
        r = self.client.get("/atencion/bandeja-entrada")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r["Location"])
        self.assertIn("next=", r["Location"])
        self.assertIn("bandeja-entrada", r["Location"])

    def test_anonimo_en_otra_seccion_spa_tambien_redirige(self):
        r = self.client.get("/comercial/clientes")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r["Location"])

    def test_login_es_publico(self):
        r = self.client.get("/login")
        self.assertEqual(r.status_code, 200)
        self.assertIn("no-store", r["Cache-Control"])

    def test_registro_es_publico(self):
        self.assertEqual(self.client.get("/register").status_code, 200)

    def test_autenticado_recibe_el_shell(self):
        self.client.force_login(self.user)
        r = self.client.get("/atencion/bandeja-entrada")
        self.assertEqual(r.status_code, 200)


class DebugRedisAuthTests(TestCase):
    URL = "/dashboard/whatsapp/api/debug-redis/"

    def test_anonimo_no_entra(self):
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r["Location"])

    def test_usuario_normal_no_entra(self):
        u = User.objects.create_user("plain", password="x")
        self.client.force_login(u)
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 302)

    def test_superusuario_si_entra(self):
        su = User.objects.create_superuser("root", "root@x.com", "x")
        self.client.force_login(su)
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 200)
