"""API v2 de Personal — contrato, CRUD, RBAC, mapeo inglés↔español.

Referencia del patrón para el resto de módulos (ver docs/PATRON-API-VUE.md).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.campo.models import Ayudante, Conductor
from apps.campo.api.mappers import (
    ASSISTANT_FIELDS, DRIVER_FIELDS, api_to_model, model_to_api,
)
from apps.campo.api.serializers import DriverSerializer

User = get_user_model()


class MapperRoundTripTests(APITestCase):
    def test_ida_y_vuelta_conductor(self):
        api = {"name": "Ana", "documentId": "1", "phone": "9", "licenseNumber": "L",
               "licenseCategory": "A-I", "licenseExpiresOn": "2027-01-01",
               "active": True, "notes": "ok"}
        model = api_to_model(DRIVER_FIELDS, api)
        self.assertEqual(set(model), {
            "nombre", "dni", "telefono", "numero_licencia", "categoria_licencia",
            "fecha_vencimiento_licencia", "activo", "observaciones",
        })
        self.assertEqual(model_to_api(DRIVER_FIELDS, model), api)

    def test_serializer_expone_exactamente_las_claves_del_mapa(self):
        # El serializer no debe exponer ninguna clave en español ni omitir ninguna
        # del contrato (salvo 'id', que no está en el mapa).
        expuestas = set(DriverSerializer().fields) - {"id"}
        self.assertEqual(expuestas, set(DRIVER_FIELDS))

    def test_ayudante_no_tiene_campos_de_licencia(self):
        self.assertNotIn("licenseNumber", ASSISTANT_FIELDS)


class _Authed(APITestCase):
    role = "Supervisor"

    def setUp(self):
        self.user = User.objects.create_user("api_user", password="x")
        if self.role:
            g, _ = Group.objects.get_or_create(name=self.role)
            self.user.groups.add(g)
        self.client.force_login(self.user)


class DriverApiTests(_Authed):
    def test_lista_formato_estandar(self):
        Conductor.objects.create(nombre="Uno", dni="d1", telefono="1")
        r = self.client.get("/api/v2/drivers/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.data), {"results", "page", "pageSize", "total", "pages"})
        self.assertEqual(r.data["results"][0]["name"], "Uno")
        self.assertNotIn("nombre", r.data["results"][0])

    def test_crear_traduce_a_espanol_en_bd(self):
        r = self.client.post("/api/v2/drivers/", {
            "name": "Nuevo", "documentId": "99", "phone": "555",
            "licenseCategory": "A-III-a",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        c = Conductor.objects.get(dni="99")
        self.assertEqual(c.nombre, "Nuevo")
        self.assertEqual(c.categoria_licencia, "A-III-a")

    def test_documento_duplicado_da_error_por_campo(self):
        Conductor.objects.create(nombre="X", dni="dup", telefono="1")
        r = self.client.post("/api/v2/drivers/", {
            "name": "Y", "documentId": "dup", "phone": "2",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("documentId", r.data["fields"])
        self.assertIn("error", r.data)

    def test_patch_parcial(self):
        c = Conductor.objects.create(nombre="Z", dni="z1", telefono="1")
        r = self.client.patch(f"/api/v2/drivers/{c.id}/", {"phone": "999"}, format="json")
        self.assertEqual(r.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.telefono, "999")
        self.assertEqual(c.nombre, "Z")

    def test_toggle_active(self):
        c = Conductor.objects.create(nombre="T", dni="t1", telefono="1", activo=True)
        r = self.client.post(f"/api/v2/drivers/{c.id}/toggle-active/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["active"])
        c.refresh_from_db()
        self.assertFalse(c.activo)

    def test_busqueda_y_filtro_estado(self):
        Conductor.objects.create(nombre="Buscable", dni="b1", telefono="1", activo=True)
        Conductor.objects.create(nombre="Otro", dni="o1", telefono="2", activo=False)
        self.assertEqual(len(self.client.get("/api/v2/drivers/?search=buscable").data["results"]), 1)
        self.assertEqual(len(self.client.get("/api/v2/drivers/?status=inactive").data["results"]), 1)

    def test_delete(self):
        c = Conductor.objects.create(nombre="D", dni="d9", telefono="1")
        self.assertEqual(self.client.delete(f"/api/v2/drivers/{c.id}/").status_code, 204)
        self.assertFalse(Conductor.objects.filter(pk=c.id).exists())


class AssistantApiTests(_Authed):
    def test_crud_minimo(self):
        r = self.client.post("/api/v2/assistants/", {
            "name": "Ayu", "documentId": "a1", "phone": "1",
        }, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertTrue(Ayudante.objects.filter(dni="a1").exists())


class RbacTests(APITestCase):
    def test_anonimo_401(self):
        self.assertIn(self.client.get("/api/v2/drivers/").status_code, (401, 403))

    def test_usuario_sin_rol_403(self):
        u = User.objects.create_user("norole", password="x")
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/drivers/").status_code, 403)

    def test_asesor_de_ventas_si(self):
        u = User.objects.create_user("asesor", password="x")
        g, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        u.groups.add(g)
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/drivers/").status_code, 200)

    def test_superusuario_si(self):
        u = User.objects.create_superuser("su", "su@x.com", "x")
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/drivers/").status_code, 200)


class AuthPayloadTests(APITestCase):
    def test_user_endpoint_incluye_roles(self):
        u = User.objects.create_user("roled", password="x")
        g, _ = Group.objects.get_or_create(name="Supervisor")
        u.groups.add(g)
        self.client.force_login(u)
        r = self.client.get("/dashboard/api/auth/user/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user"]["roles"], ["Supervisor"])

    def test_superusuario_recibe_administrador(self):
        u = User.objects.create_superuser("su2", "su2@x.com", "x")
        self.client.force_login(u)
        r = self.client.get("/dashboard/api/auth/user/")
        self.assertIn("Administrador", r.json()["user"]["roles"])
