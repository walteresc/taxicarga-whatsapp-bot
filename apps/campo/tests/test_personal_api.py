import json

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from apps.campo.models import Ayudante, Conductor


class PersonalApiBase(TestCase):
    def setUp(self):
        group, _ = Group.objects.get_or_create(name="Supervisor")
        self.user = User.objects.create_user("personal_manager", password="test-pass")
        self.user.groups.add(group)

    def login(self):
        self.client.force_login(self.user)

    def json_request(self, method, url, payload=None):
        return getattr(self.client, method)(
            url,
            data=json.dumps(payload or {}),
            content_type="application/json",
        )


class ConductoresApiTests(PersonalApiBase):
    def setUp(self):
        super().setUp()
        self.list_url = reverse("api-personal-conductores")

    def test_requiere_autenticacion(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)

    def test_requiere_rol_permitido(self):
        outsider = User.objects.create_user("outsider", password="test-pass")
        self.client.force_login(outsider)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_crear_y_editar_conductor(self):
        self.login()
        response = self.json_request("post", self.list_url, {
            "nombre": "Juan Pérez",
            "dni": "12345678",
            "telefono": "51970000001",
            "numero_licencia": "Q12345678",
            "categoria_licencia": "A-III-c",
            "fecha_vencimiento_licencia": "2027-08-27",
            "activo": True,
        })
        self.assertEqual(response.status_code, 201)
        conductor_id = response.json()["id"]

        response = self.json_request(
            "patch",
            reverse("api-personal-conductor", args=[conductor_id]),
            {"telefono": "51971111111", "activo": False},
        )
        self.assertEqual(response.status_code, 200)
        conductor = Conductor.objects.get(pk=conductor_id)
        self.assertEqual(conductor.telefono, "51971111111")
        self.assertFalse(conductor.activo)

    def test_lista_filtra_y_pagina(self):
        self.login()
        Conductor.objects.create(nombre="Ana Activa", dni="10000001", telefono="511", activo=True)
        Conductor.objects.create(nombre="Luis Inactivo", dni="10000002", telefono="512", activo=False)

        response = self.client.get(self.list_url, {"search": "Ana", "status": "active", "page_size": 1})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["results"][0]["nombre"], "Ana Activa")

    def test_dni_duplicado_devuelve_error(self):
        self.login()
        Conductor.objects.create(nombre="Uno", dni="12345678", telefono="511")
        response = self.json_request("post", self.list_url, {
            "nombre": "Dos", "dni": "12345678", "telefono": "512",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("dni", response.json()["errors"])

    def test_no_admite_eliminacion(self):
        self.login()
        conductor = Conductor.objects.create(nombre="Uno", dni="12345678", telefono="511")
        response = self.client.delete(reverse("api-personal-conductor", args=[conductor.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Conductor.objects.filter(pk=conductor.pk).exists())


class AyudantesApiTests(PersonalApiBase):
    def setUp(self):
        super().setUp()
        self.list_url = reverse("api-personal-ayudantes")

    def test_crear_editar_y_listar_ayudante(self):
        self.login()
        response = self.json_request("post", self.list_url, {
            "nombre": "Pedro Gómez",
            "dni": "87654321",
            "telefono": "51970000002",
            "observaciones": "Disponible fines de semana",
        })
        self.assertEqual(response.status_code, 201)
        ayudante_id = response.json()["id"]

        response = self.json_request(
            "patch",
            reverse("api-personal-ayudante", args=[ayudante_id]),
            {"nombre": "Pedro Gómez R.", "activo": False},
        )
        self.assertEqual(response.status_code, 200)
        ayudante = Ayudante.objects.get(pk=ayudante_id)
        self.assertEqual(ayudante.nombre, "Pedro Gómez R.")
        self.assertFalse(ayudante.activo)

        response = self.client.get(self.list_url, {"status": "inactive"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)

    def test_campos_obligatorios(self):
        self.login()
        response = self.json_request("post", self.list_url, {"nombre": "Incompleto"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("dni", response.json()["errors"])
        self.assertIn("telefono", response.json()["errors"])
