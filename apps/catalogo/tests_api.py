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
    """La compatibilidad es por CATEGORÍA puntual (tonelaje), no por tipo de
    vehículo genérico — un "Camión 2 ton" y un "Camión 15 ton" pueden admitir
    carrocerías distintas."""

    def test_patch_sincroniza_compatibilidades(self):
        categoria = CategoriaVehiculo.objects.get(nombre="Camioneta")
        pickup = TipoCarroceria.objects.get(codigo="pickup")
        furgon = TipoCarroceria.objects.get(codigo="furgon_cerrado")

        r = self.client.patch(
            f"/api/v2/vehicle-categories/{categoria.id}/",
            {"compatibleBodyTypeIds": [pickup.id, furgon.id]}, format="json",
        )
        self.assertEqual(r.status_code, 200)
        got = set(
            CompatibilidadCarroceria.objects
            .filter(categoria_vehiculo=categoria).values_list("tipo_carroceria__codigo", flat=True)
        )
        self.assertEqual(got, {"pickup", "furgon_cerrado"})

    def test_patch_vacio_deja_sin_carroceria(self):
        categoria = CategoriaVehiculo.objects.get(nombre="Camión 2 ton")
        r = self.client.patch(
            f"/api/v2/vehicle-categories/{categoria.id}/",
            {"compatibleBodyTypeIds": []}, format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(CompatibilidadCarroceria.objects.filter(categoria_vehiculo=categoria).count(), 0)

    def test_nombre_cliente_se_guarda_y_se_lee(self):
        categoria = CategoriaVehiculo.objects.get(nombre="Camión 30 ton")
        furgon = TipoCarroceria.objects.get(codigo="furgon_cerrado")
        plataforma = TipoCarroceria.objects.get(codigo="plataforma")

        r = self.client.patch(
            f"/api/v2/vehicle-categories/{categoria.id}/",
            {
                "compatibleBodyTypeIds": [furgon.id, plataforma.id],
                "bodyTypeDisplayNames": {str(furgon.id): "Cigüeña"},
                "bodyTypeWeightCategories": {str(furgon.id): "especiales"},
            }, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        by_id = {c["id"]: c for c in r.data["compatibleBodyTypes"]}
        self.assertEqual(by_id[furgon.id]["displayName"], "Cigüeña")
        self.assertEqual(by_id[furgon.id]["weightCategory"], "especiales")
        self.assertEqual(by_id[plataforma.id]["displayName"], "")
        self.assertEqual(by_id[plataforma.id]["weightCategory"], "")

    def test_categorias_del_mismo_tipo_no_comparten_compatibilidad(self):
        """Regresion: antes CompatibilidadCarroceria colgaba de TipoVehiculo,
        asi que TODAS las categorias de "Camion" (2 ton .. 15 ton)
        terminaban con la misma lista de carrocerias compatibles. El seed
        arranca compartido (la migracion copia la lista vieja a cada
        categoria como punto de partida) — lo que se prueba acá es que,
        una vez que un admin afina una categoria por separado, la otra NO
        se ve afectada (algo imposible con el modelo viejo)."""
        liviano = CategoriaVehiculo.objects.get(nombre="Camión 2 ton")
        pesado = CategoriaVehiculo.objects.get(nombre="Camión 15 ton")
        volquete = TipoCarroceria.objects.get(codigo="volquete")
        furgon = TipoCarroceria.objects.get(codigo="furgon_cerrado")

        self.client.patch(
            f"/api/v2/vehicle-categories/{liviano.id}/",
            {"compatibleBodyTypeIds": [furgon.id]}, format="json",
        )
        self.client.patch(
            f"/api/v2/vehicle-categories/{pesado.id}/",
            {"compatibleBodyTypeIds": [volquete.id]}, format="json",
        )
        r = self.client.get(f"/api/v2/vehicle-categories/{liviano.id}/")
        self.assertEqual(r.status_code, 200)
        got = [c["id"] for c in r.data["compatibleBodyTypes"]]
        self.assertEqual(got, [furgon.id])
        self.assertNotIn(volquete.id, got)


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


class PublicVehiclePickerTests(APITestCase):
    """Sin login — lo usa el selector de vehículo del cotizador de invitado."""
    def test_sin_login_devuelve_solo_camioneta_y_camion(self):
        r = self.client.get("/api/v2/catalog/vehicle-picker")
        self.assertEqual(r.status_code, 200, r.content)
        vehicle_types = {u["vehicleType"] for u in r.data["units"]}
        self.assertEqual(vehicle_types, {"camioneta", "camion"})
        self.assertTrue(any(u["name"] == "Camión 2 ton" for u in r.data["units"]))

    def test_no_incluye_moto_ni_semitrailer(self):
        r = self.client.get("/api/v2/catalog/vehicle-picker")
        vehicle_types = {u["vehicleType"] for u in r.data["units"]}
        self.assertNotIn("moto", vehicle_types)
        self.assertNotIn("semitrailer", vehicle_types)

    def test_body_types_solo_habilitados_y_compatibles(self):
        r = self.client.get("/api/v2/catalog/vehicle-picker")
        codes = {b["code"] for b in r.data["bodyTypes"]}
        self.assertIn("furgon_cerrado", codes)
        self.assertIn("plataforma", codes)

    def test_nombre_cliente_crea_unidad_virtual_y_no_duplica_carroceria(self):
        """Una combinación categoría+carrocería con nombre_cliente (p. ej.
        "Cigüeña") se muestra como su propia unidad con nombre propio y
        carrocería fija, y deja de listarse como una carrocería más dentro
        de la unidad real de esa categoría."""
        categoria = CategoriaVehiculo.objects.get(nombre="Camión 2 ton")
        furgon = TipoCarroceria.objects.get(codigo="furgon_cerrado")
        CompatibilidadCarroceria.objects.filter(
            categoria_vehiculo=categoria, tipo_carroceria=furgon,
        ).update(nombre_cliente="Cigüeña")

        r = self.client.get("/api/v2/catalog/vehicle-picker")
        self.assertEqual(r.status_code, 200, r.content)
        virtual = next((u for u in r.data["units"] if u["name"] == "Cigüeña"), None)
        self.assertIsNotNone(virtual)
        self.assertEqual(virtual["fixedBodyType"], "furgon_cerrado")
        self.assertEqual(virtual["vehicleType"], "camion")

        base = next(u for u in r.data["units"] if u["name"] == "Camión 2 ton")
        self.assertNotIn("furgon_cerrado", base["bodyTypes"])

    def test_categoria_cliente_permite_mostrar_en_otra_categoria_de_peso(self):
        """"Camión 2 ton" es "livianos", pero la variante grúa de esa misma
        categoría real se puede mostrar al cliente en "Especiales" sin
        afectar la categoría de peso real de "Camión 2 ton"."""
        categoria = CategoriaVehiculo.objects.get(nombre="Camión 2 ton")
        self.assertEqual(categoria.categoria, "livianos")
        grua = TipoCarroceria.objects.get(codigo="grua_telescopica")
        CompatibilidadCarroceria.objects.filter(
            categoria_vehiculo=categoria, tipo_carroceria=grua,
        ).update(nombre_cliente="Camión Grúa 2 ton", categoria_cliente="especiales")

        r = self.client.get("/api/v2/catalog/vehicle-picker")
        virtual = next(u for u in r.data["units"] if u["name"] == "Camión Grúa 2 ton")
        self.assertEqual(virtual["weightCategory"], "especiales")

        base = next(u for u in r.data["units"] if u["name"] == "Camión 2 ton")
        self.assertEqual(base["weightCategory"], "livianos")

    def test_todas_agrupa_por_categoria_de_peso_no_solo_por_orden(self):
        """Sin filtrar por categoría de peso, las unidades se agrupan por
        categoría de peso (Livianos, Medianos, Pesados, Especiales, en ese
        orden) — no solo por el "Orden" global. Una unidad "Especiales"
        armada sobre una categoría real de "Livianos" con orden bajo (2 ton
        es de las primeras) no debe intercalarse entre los ítems de
        Livianos."""
        categoria = CategoriaVehiculo.objects.get(nombre="Camión 2 ton")
        grua = TipoCarroceria.objects.get(codigo="grua_telescopica")
        CompatibilidadCarroceria.objects.filter(
            categoria_vehiculo=categoria, tipo_carroceria=grua,
        ).update(nombre_cliente="Camión Grúa 2 ton", categoria_cliente="especiales")

        r = self.client.get("/api/v2/catalog/vehicle-picker")
        idx_grua = next(i for i, u in enumerate(r.data["units"]) if u["name"] == "Camión Grúa 2 ton")
        idx_ultimo_liviano = max(
            i for i, u in enumerate(r.data["units"]) if u["weightCategory"] == "livianos"
        )
        self.assertGreater(idx_grua, idx_ultimo_liviano)
