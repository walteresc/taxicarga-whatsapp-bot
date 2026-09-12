"""Fotos del vehículo del transportista (2026-09): 3 cupos fijos, subidos
desde el Portal del Transportista; visibles para el staff del CRM desde
`carrier-vehicles`."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from apps.catalogo.models import TipoVehiculo
from apps.tercerizacion.models import Transportista, TransportistaVehiculo

User = get_user_model()


def _archivo(nombre="foto.jpg"):
    return SimpleUploadedFile(nombre, b"contenido-de-prueba", content_type="image/jpeg")


def _carrier_con_vehiculo(name="X"):
    u = User.objects.create_user(f"carr_{name}", password="x")
    u.groups.add(Group.objects.get_or_create(name="Transportista")[0])
    c = Transportista.objects.create(nombre=f"Transportes {name}", usuario=u)
    tv = TipoVehiculo.objects.get(codigo="camion")
    v = TransportistaVehiculo.objects.create(transportista=c, placa=f"{name}00-100", tipo_vehiculo=tv)
    return c, u, v


class PortalVehiclePhotosTests(APITestCase):
    def setUp(self):
        self.carrier, self.user, self.vehicle = _carrier_con_vehiculo("A")
        self.client.force_authenticate(self.user)

    def test_lista_mis_vehiculos_sin_fotos(self):
        r = self.client.get("/api/v2/portal/carrier/vehicles")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(r.data["results"]), 1)
        self.assertEqual(r.data["results"][0]["photos"], [None, None, None])

    def test_sube_una_foto_y_queda_en_el_cupo_correcto(self):
        r = self.client.post(
            f"/api/v2/portal/carrier/vehicles/{self.vehicle.id}/photos",
            {"photo2": _archivo()}, format="multipart",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIsNone(r.data["photos"][0])
        self.assertIsNotNone(r.data["photos"][1])
        self.assertIsNone(r.data["photos"][2])

    def test_sube_las_3_a_la_vez(self):
        r = self.client.post(
            f"/api/v2/portal/carrier/vehicles/{self.vehicle.id}/photos",
            {"photo1": _archivo("a.jpg"), "photo2": _archivo("b.jpg"), "photo3": _archivo("c.jpg")},
            format="multipart",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(all(r.data["photos"]))

    def test_sin_archivos_rechaza(self):
        r = self.client.post(f"/api/v2/portal/carrier/vehicles/{self.vehicle.id}/photos", {}, format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_no_puede_subir_a_vehiculo_de_otro_transportista(self):
        _otro_carrier, _otro_user, otro_vehicle = _carrier_con_vehiculo("B")
        r = self.client.post(
            f"/api/v2/portal/carrier/vehicles/{otro_vehicle.id}/photos",
            {"photo1": _archivo()}, format="multipart",
        )
        self.assertEqual(r.status_code, 404)

    def test_descarga_la_foto_subida(self):
        self.client.post(
            f"/api/v2/portal/carrier/vehicles/{self.vehicle.id}/photos",
            {"photo1": _archivo()}, format="multipart",
        )
        r = self.client.get(f"/api/v2/portal/carrier/vehicles/{self.vehicle.id}/photo/1")
        self.assertEqual(r.status_code, 200)

    def test_cupo_vacio_da_404(self):
        r = self.client.get(f"/api/v2/portal/carrier/vehicles/{self.vehicle.id}/photo/1")
        self.assertEqual(r.status_code, 404)


class CrmVehiclePhotosTests(APITestCase):
    def setUp(self):
        self.carrier, self.user, self.vehicle = _carrier_con_vehiculo("C")
        self.staff = User.objects.create_user("staff_test", password="x")
        self.staff.groups.add(Group.objects.get_or_create(name="Despacho")[0])

    def test_serializer_expone_photos(self):
        self.client.force_authenticate(self.staff)
        r = self.client.get(f"/api/v2/carrier-vehicles/{self.vehicle.id}/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["photos"], [None, None, None])

    def test_staff_puede_ver_la_foto_que_subio_el_transportista(self):
        self.client.force_authenticate(self.user)
        self.client.post(
            f"/api/v2/portal/carrier/vehicles/{self.vehicle.id}/photos",
            {"photo1": _archivo()}, format="multipart",
        )
        self.client.force_authenticate(self.staff)
        r = self.client.get(f"/api/v2/carrier-vehicles/{self.vehicle.id}/photo/1")
        self.assertEqual(r.status_code, 200)

    def test_sin_rol_no_puede(self):
        sin_rol = User.objects.create_user("sin_rol_test", password="x")
        self.client.force_authenticate(sin_rol)
        r = self.client.get(f"/api/v2/carrier-vehicles/{self.vehicle.id}/photo/1")
        self.assertEqual(r.status_code, 403)
