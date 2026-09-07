"""API v2 de Flota — vehículos, mantenimientos y avisos de vencimientos."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.campo.models import Vehiculo
from apps.flota.models import MantenimientoVehiculo
from apps.flota.api.mappers import (
    MAINTENANCE_FIELDS, VEHICLE_FIELDS, api_to_model, model_to_api,
)
from apps.flota.api.serializers import MaintenanceSerializer, VehicleSerializer

User = get_user_model()


def _vehiculo(**kw):
    base = dict(placa="ABC-100", marca="Volvo", modelo="FH", capacidad_toneladas="10.00")
    base.update(kw)
    return Vehiculo.objects.create(**base)


class MapperRoundTripTests(APITestCase):
    def test_vehiculo_ida_y_vuelta(self):
        api = {"plate": "P", "brand": "B", "model": "M", "year": 2020,
               "capacityTons": "10.00", "capacityM3": "30.00",
               "soatExpiresOn": "2027-01-01", "technicalReviewExpiresOn": "2027-02-01",
               "fireExtinguisherExpiresOn": "2027-03-01", "active": True, "notes": "x"}
        model = api_to_model(VEHICLE_FIELDS, api)
        self.assertEqual(model_to_api(VEHICLE_FIELDS, model), api)

    def test_serializers_exponen_las_claves_del_mapa(self):
        self.assertEqual(set(VehicleSerializer().fields) - {"id"}, set(VEHICLE_FIELDS))
        # maintenance añade vehiclePlate (solo lectura) sobre el mapa
        self.assertEqual(
            set(MaintenanceSerializer().fields) - {"id", "vehiclePlate"},
            set(MAINTENANCE_FIELDS),
        )


class _Authed(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("flota_user", password="x")
        g, _ = Group.objects.get_or_create(name="Supervisor")
        self.user.groups.add(g)
        self.client.force_login(self.user)


class VehicleApiTests(_Authed):
    def test_crear_y_traducir(self):
        r = self.client.post("/api/v2/vehicles/", {
            "plate": "XYZ-1", "brand": "Scania", "model": "R", "capacityTons": "12.5",
            "soatExpiresOn": "2027-06-01",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        v = Vehiculo.objects.get(placa="XYZ-1")
        self.assertEqual(v.marca, "Scania")
        self.assertEqual(str(v.fecha_vencimiento_soat), "2027-06-01")

    def test_placa_duplicada(self):
        _vehiculo(placa="DUP-1")
        r = self.client.post("/api/v2/vehicles/", {
            "plate": "DUP-1", "brand": "x", "model": "y", "capacityTons": "1",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("plate", r.data["fields"])

    def test_toggle_active(self):
        v = _vehiculo(activo=True)
        r = self.client.post(f"/api/v2/vehicles/{v.id}/toggle-active/")
        self.assertFalse(r.data["active"])

    def test_lista_ingles(self):
        _vehiculo(placa="LST-1")
        row = self.client.get("/api/v2/vehicles/").data["results"][0]
        self.assertIn("plate", row)
        self.assertNotIn("placa", row)


class MaintenanceApiTests(_Authed):
    def test_crear_con_vehicleId(self):
        v = _vehiculo()
        r = self.client.post("/api/v2/maintenance/", {
            "vehicleId": v.id, "performedOn": "2026-08-01", "odometer": 40000,
            "nextServiceOdometer": 50000, "work": "Cambio de aceite",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["vehiclePlate"], v.placa)
        self.assertTrue(MantenimientoVehiculo.objects.filter(vehiculo=v).exists())

    def test_proximo_km_debe_ser_mayor(self):
        v = _vehiculo()
        r = self.client.post("/api/v2/maintenance/", {
            "vehicleId": v.id, "performedOn": "2026-08-01", "odometer": 50000,
            "nextServiceOdometer": 40000, "work": "x",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("nextServiceOdometer", r.data["fields"])

    def test_filtro_por_vehiculo(self):
        v1, v2 = _vehiculo(placa="V1"), _vehiculo(placa="V2")
        MantenimientoVehiculo.objects.create(
            vehiculo=v1, fecha_mantenimiento=dt.date(2026, 1, 1),
            kilometraje_actual=1, proximo_mantenimiento_km=2, descripcion="a",
        )
        MantenimientoVehiculo.objects.create(
            vehiculo=v2, fecha_mantenimiento=dt.date(2026, 1, 1),
            kilometraje_actual=1, proximo_mantenimiento_km=2, descripcion="b",
        )
        r = self.client.get(f"/api/v2/maintenance/?vehicleId={v1.id}")
        self.assertEqual(len(r.data["results"]), 1)


class AlertsTests(_Authed):
    def test_documento_vencido_y_por_vencer(self):
        hoy = timezone.localdate()
        _vehiculo(placa="OK-1", fecha_vencimiento_soat=hoy + dt.timedelta(days=200))
        _vehiculo(placa="VENC-1", fecha_vencimiento_soat=hoy - dt.timedelta(days=5))
        _vehiculo(placa="PRONTO-1", fecha_vencimiento_rtv=hoy + dt.timedelta(days=10))

        data = self.client.get("/api/v2/vehicles/alerts/").data
        placas = {it["plate"] for it in data}
        self.assertEqual(placas, {"VENC-1", "PRONTO-1"})
        # ordenado: vencido antes que por vencer
        self.assertEqual(data[0]["plate"], "VENC-1")
        self.assertEqual(data[0]["worstStatus"], "overdue")

    def test_aviso_por_kilometraje(self):
        v = _vehiculo(placa="KM-1")
        MantenimientoVehiculo.objects.create(
            vehiculo=v, fecha_mantenimiento=timezone.localdate(),
            kilometraje_actual=49500, proximo_mantenimiento_km=50000, descripcion="x",
        )
        data = self.client.get("/api/v2/vehicles/alerts/").data
        km = [a for it in data if it["plate"] == "KM-1" for a in it["alerts"] if a["type"] == "service"]
        self.assertEqual(len(km), 1)
        self.assertEqual(km[0]["remainingKm"], 500)
        self.assertEqual(km[0]["status"], "due_soon")

    def test_vehiculo_inactivo_no_alerta(self):
        hoy = timezone.localdate()
        _vehiculo(placa="INACT", activo=False, fecha_vencimiento_soat=hoy - dt.timedelta(days=5))
        self.assertEqual(self.client.get("/api/v2/vehicles/alerts/").data, [])


class RbacTests(APITestCase):
    def test_sin_rol_403(self):
        u = User.objects.create_user("nr", password="x")
        self.client.force_login(u)
        self.assertEqual(self.client.get("/api/v2/vehicles/").status_code, 403)
        self.assertEqual(self.client.get("/api/v2/vehicles/alerts/").status_code, 403)
