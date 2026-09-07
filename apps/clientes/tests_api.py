"""API v2 de Clientes — contrato, CRUD sin borrado duro, teléfono, RBAC."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente
from apps.clientes.api.mappers import CUSTOMER_FIELDS, api_to_model, model_to_api
from apps.clientes.api.serializers import CustomerSerializer

User = get_user_model()


class MapperRoundTripTests(APITestCase):
    def test_ida_y_vuelta(self):
        api = {"name": "Ana", "phone": "1", "documentId": "d", "email": "a@b.co",
               "taxId": "r", "businessName": "SA", "active": True}
        self.assertEqual(model_to_api(CUSTOMER_FIELDS, api_to_model(CUSTOMER_FIELDS, api)), api)

    def test_serializer_expone_las_claves_del_mapa_mas_las_de_solo_lectura(self):
        ro = {"id", "displayName", "contactId", "hasRealPhone", "isTransportista", "createdAt"}
        self.assertEqual(set(CustomerSerializer().fields) - ro, set(CUSTOMER_FIELDS))


class _Authed(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("cli_user", password="x")
        g, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        self.user.groups.add(g)
        self.client.force_login(self.user)


class CustomerApiTests(_Authed):
    def test_crear_normaliza_telefono(self):
        r = self.client.post("/api/v2/customers/", {
            "name": "Nuevo", "phone": "995403320",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        c = Cliente.objects.get(nombre="Nuevo")
        self.assertEqual(c.telefono, "+51995403320")
        self.assertEqual(r.data["phone"], "+51995403320")

    def test_telefono_duplicado_detecta_aunque_formato_distinto(self):
        Cliente.objects.create(nombre="X", telefono="+51999888777")
        r = self.client.post("/api/v2/customers/", {
            "name": "Y", "phone": "999 888 777",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("phone", r.data["fields"])

    def test_lista_ingles_y_campos_solo_lectura(self):
        Cliente.objects.create(nombre="Listado", telefono="+51900000001")
        row = self.client.get("/api/v2/customers/").data["results"][0]
        self.assertIn("name", row)
        self.assertNotIn("nombre", row)
        self.assertIn("contactId", row)
        self.assertIn("hasRealPhone", row)

    def test_patch(self):
        c = Cliente.objects.create(nombre="Edit", telefono="+51900000002")
        r = self.client.patch(f"/api/v2/customers/{c.id}/", {"email": "e@x.co"}, format="json")
        self.assertEqual(r.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.correo, "e@x.co")

    def test_toggle_active_es_soft_delete(self):
        c = Cliente.objects.create(nombre="Soft", telefono="+51900000003", is_active=True)
        r = self.client.post(f"/api/v2/customers/{c.id}/toggle-active/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["active"])
        self.assertTrue(Cliente.objects.filter(pk=c.id).exists())  # NO se borró

    def test_delete_no_permitido(self):
        c = Cliente.objects.create(nombre="NoDel", telefono="+51900000004")
        self.assertEqual(self.client.delete(f"/api/v2/customers/{c.id}/").status_code, 405)

    def test_filtro_status(self):
        Cliente.objects.create(nombre="A1", telefono="+51900000010", is_active=True)
        Cliente.objects.create(nombre="A2", telefono="+51900000011", is_active=False)
        self.assertEqual(len(self.client.get("/api/v2/customers/?status=inactive").data["results"]), 1)


class RbacTests(APITestCase):
    def test_sin_rol_403(self):
        u = User.objects.create_user("nr", password="x")
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/customers/").status_code, 403)
