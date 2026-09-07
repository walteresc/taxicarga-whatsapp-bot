"""API v2 del catálogo de vehículos: categorización automática y compatibilidades."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.catalogo.models import (
    CategoriaVehiculo, CompatibilidadCarroceria, TipoCarroceria, TipoVehiculo,
    categoria_para_capacidad,
)

User = get_user_model()


class _Base(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("cat_admin", password="x")
        self.user.groups.add(Group.objects.get_or_create(name="Administrador")[0])
        self.client.force_authenticate(self.user)


class SeedTests(_Base):
    def test_seed_cargado(self):
        self.assertEqual(TipoVehiculo.objects.count(), 7)
        self.assertEqual(TipoCarroceria.objects.count(), 14)
        self.assertEqual(CategoriaVehiculo.objects.count(), 23)


class CategorizacionTests(_Base):
    def test_categoria_por_capacidad(self):
        camion = TipoVehiculo.objects.get(codigo="camion")
        self.assertEqual(categoria_para_capacidad(camion.id, Decimal("6.5")).nombre, "Camión 6 ton")
        self.assertEqual(categoria_para_capacidad(camion.id, Decimal("18")).categoria, "pesados")

    def test_tipo_sin_rango_devuelve_primera_fila(self):
        moto = TipoVehiculo.objects.get(codigo="moto")
        self.assertEqual(categoria_para_capacidad(moto.id, None).nombre, "Moto")


class CompatibilidadesApiTests(_Base):
    def test_patch_sincroniza_compatibilidades(self):
        camioneta = TipoVehiculo.objects.get(codigo="camioneta")
        pickup = TipoCarroceria.objects.get(codigo="pickup")
        furgon = TipoCarroceria.objects.get(codigo="furgon_cerrado")

        r = self.client.patch(
            f"/api/v2/vehicle-types/{camioneta.id}/",
            {"compatibleBodyTypeIds": [pickup.id, furgon.id]}, format="json",
        )
        self.assertEqual(r.status_code, 200)
        got = set(
            CompatibilidadCarroceria.objects
            .filter(tipo_vehiculo=camioneta).values_list("tipo_carroceria__codigo", flat=True)
        )
        self.assertEqual(got, {"pickup", "furgon_cerrado"})

    def test_patch_vacio_deja_sin_carroceria(self):
        camion = TipoVehiculo.objects.get(codigo="camion")
        r = self.client.patch(
            f"/api/v2/vehicle-types/{camion.id}/",
            {"compatibleBodyTypeIds": []}, format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(CompatibilidadCarroceria.objects.filter(tipo_vehiculo=camion).count(), 0)


class CategoriaCrudApiTests(_Base):
    def test_crear_y_toggle(self):
        tv = TipoVehiculo.objects.get(codigo="camion")
        r = self.client.post("/api/v2/vehicle-categories/", {
            "vehicleTypeId": tv.id, "name": "Camión 100 ton", "category": "pesados",
            "minTons": "60", "maxTons": "120", "order": 99,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        cid = r.data["id"]
        r = self.client.post(f"/api/v2/vehicle-categories/{cid}/toggle-active/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["enabled"])
