"""API v2: transportistas afiliados y sus vehículos (categoría automática)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.catalogo.models import TipoVehiculo
from apps.tercerizacion.models import Transportista, TransportistaVehiculo

User = get_user_model()


class _Base(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("carr_user", password="x")
        self.user.groups.add(Group.objects.get_or_create(name="Asesor de Ventas")[0])
        self.client.force_authenticate(self.user)


class CarrierFlowTests(_Base):
    def test_alta_transportista_y_vehiculo_asigna_categoria(self):
        r = self.client.post("/api/v2/carriers/", {
            "name": "Transportes ABC", "documentId": "20111", "isDriver": True,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        carrier_id = r.data["id"]

        camion = TipoVehiculo.objects.get(codigo="camion")
        r = self.client.post("/api/v2/carrier-vehicles/", {
            "carrierId": carrier_id, "plate": "XYZ-987",
            "vehicleTypeId": camion.id, "capacityUsefulTons": "12",
            "lengthUsefulM": "6.5", "widthUsefulM": "2.4", "heightUsefulM": "2.6",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["categoryName"], "Camión 12 ton")

        veh = TransportistaVehiculo.objects.get(placa="XYZ-987")
        self.assertEqual(veh.categoria.categoria, "medianos")

        # el conteo de vehículos aparece en el listado de transportistas
        r = self.client.get("/api/v2/carriers/")
        self.assertEqual(r.data["results"][0]["vehicleCount"], 1)

    def test_alta_con_direccion_y_ubicacion_frecuente(self):
        r = self.client.post("/api/v2/carriers/", {
            "name": "Transportes Provincia", "address": "Jr. Los Andes 200",
            "homeCity": "Arequipa",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["address"], "Jr. Los Andes 200")
        self.assertEqual(r.data["homeCity"], "Arequipa")
        carrier = Transportista.objects.get(pk=r.data["id"])
        self.assertEqual(carrier.direccion, "Jr. Los Andes 200")
        self.assertEqual(carrier.ubicacion_frecuente, "Arequipa")

    def test_placa_duplicada_rechazada(self):
        c = Transportista.objects.create(nombre="T1")
        camion = TipoVehiculo.objects.get(codigo="camion")
        TransportistaVehiculo.objects.create(transportista=c, placa="DUP-111", tipo_vehiculo=camion)
        r = self.client.post("/api/v2/carrier-vehicles/", {
            "carrierId": c.id, "plate": "DUP-111", "vehicleTypeId": camion.id,
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("plate", r.data.get("fields", r.data))


class ParaUbicacionTests(APITestCase):
    def test_case_insensitive_y_solo_activos(self):
        Transportista.objects.create(nombre="T1", ubicacion_frecuente="Arequipa")
        Transportista.objects.create(nombre="T2", ubicacion_frecuente="arequipa", activo=False)
        Transportista.objects.create(nombre="T3", ubicacion_frecuente="Cusco")
        self.assertEqual(Transportista.para_ubicacion("AREQUIPA").count(), 1)
        self.assertEqual(Transportista.para_ubicacion("cusco").count(), 1)

    def test_vacio_no_devuelve_todos(self):
        Transportista.objects.create(nombre="T1", ubicacion_frecuente="Arequipa")
        self.assertEqual(Transportista.para_ubicacion("").count(), 0)
        self.assertEqual(Transportista.para_ubicacion(None).count(), 0)
