"""Encomiendas Fase 3: envío interprovincial (paquete a otra ciudad).

Reusa la tabla de carga nacional parcial (`apps.tercerizacion.TarifaCargaParcial`)
para el precio del tramo troncal — no hay ZonaReparto/TarifaZona fuera de Lima.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from apps.encomiendas import services
from apps.encomiendas.models import Envio, EventoTracking, PuntoEntregaDestino
from apps.tercerizacion.models import TarifaCargaParcial, Transportista

User = get_user_model()


def _tarifa_arequipa():
    TarifaCargaParcial.objects.create(
        destino="arequipa", peso_desde_kg=0, peso_hasta_kg=None,
        precio_por_kg=Decimal("5"), monto_minimo=Decimal("35"), dias_estimados=4,
    )


class CotizarInterprovincialTests(APITestCase):
    def setUp(self):
        TarifaCargaParcial.objects.all().delete()

    def test_usa_tabla_de_carga_parcial(self):
        _tarifa_arequipa()
        r = services.cotizar(
            origen_distrito="Lima", destino_distrito="Arequipa",
            nivel=Envio.NIVEL_INTERPROVINCIAL, peso_kg=10,
        )
        self.assertEqual(r["price"], 50.0)  # 10 kg * 5, > mínimo 35
        self.assertEqual(r["level"], Envio.NIVEL_INTERPROVINCIAL)
        self.assertEqual(r["etaHours"], 4 * 24)

    def test_sin_tarifa_para_esa_ciudad_lanza_error(self):
        with self.assertRaises(ValidationError):
            services.cotizar(
                origen_distrito="Lima", destino_distrito="Iquitos",
                nivel=Envio.NIVEL_INTERPROVINCIAL, peso_kg=5,
            )

    def test_no_usa_zonareparto_aunque_no_haya_zonas_cargadas(self):
        # Sin seed_encomiendas (sin ZonaReparto) el nivel local fallaría por
        # "sin cobertura"; el interprovincial no debe verse afectado.
        _tarifa_arequipa()
        r = services.cotizar(
            origen_distrito="cualquier cosa", destino_distrito="arequipa",
            nivel=Envio.NIVEL_INTERPROVINCIAL, peso_kg=1,
        )
        self.assertEqual(r["price"], 35.0)  # mínimo


class CrearEnvioInterprovincialTests(APITestCase):
    def setUp(self):
        TarifaCargaParcial.objects.all().delete()
        _tarifa_arequipa()

    def _data(self, **extra):
        return dict(
            remitente_nombre="Tienda X", origen_distrito="Miraflores", origen_direccion="Av. Larco 100",
            destinatario_nombre="Ana P", destinatario_telefono="+51900111222",
            destino_distrito="Arequipa", destino_direccion="Recojo en agencia",
            nivel=Envio.NIVEL_INTERPROVINCIAL, peso_kg=Decimal("10"),
            **extra,
        )

    def test_cotiza_solo_al_crear(self):
        envio = services.crear_envio(self._data())
        self.assertEqual(envio.precio, Decimal("50"))
        self.assertEqual(envio.nivel, Envio.NIVEL_INTERPROVINCIAL)

    def test_guarda_punto_de_entrega(self):
        envio = services.crear_envio(self._data(punto_entrega_destino="Agencia Arequipa Centro"))
        self.assertEqual(envio.punto_entrega_destino, "Agencia Arequipa Centro")

    def test_ciclo_de_estados_pasa_por_en_destino(self):
        envio = services.crear_envio(self._data())
        services.registrar_evento(envio, Envio.ESTADO_ASIGNADO)
        services.registrar_evento(envio, Envio.ESTADO_RECOGIDO)
        services.registrar_evento(envio, Envio.ESTADO_EN_RUTA)
        services.registrar_evento(envio, Envio.ESTADO_EN_DESTINO, descripcion="Llegó a la agencia de Arequipa.")
        envio.refresh_from_db()
        self.assertEqual(envio.estado, Envio.ESTADO_EN_DESTINO)
        self.assertTrue(EventoTracking.objects.filter(envio=envio, estado=Envio.ESTADO_EN_DESTINO).exists())
        services.registrar_evento(envio, Envio.ESTADO_ENTREGADO, recibido_por="Ana P")
        envio.refresh_from_db()
        self.assertEqual(envio.estado, Envio.ESTADO_ENTREGADO)

    def test_en_destino_no_es_terminal_puede_fallar(self):
        envio = services.crear_envio(self._data())
        for estado in (Envio.ESTADO_ASIGNADO, Envio.ESTADO_RECOGIDO, Envio.ESTADO_EN_RUTA, Envio.ESTADO_EN_DESTINO):
            services.registrar_evento(envio, estado)
        services.registrar_evento(envio, Envio.ESTADO_FALLIDO, descripcion="Destinatario no llegó a recoger.")
        envio.refresh_from_db()
        self.assertEqual(envio.estado, Envio.ESTADO_FALLIDO)


class RepartoDestinoTests(APITestCase):
    """Fase B: reparto a domicilio en la ciudad destino, por un afiliado con
    `ubicacion_frecuente` en esa ciudad."""

    def setUp(self):
        TarifaCargaParcial.objects.all().delete()
        _tarifa_arequipa()
        self.afiliado = Transportista.objects.create(nombre="Local Arequipa", ubicacion_frecuente="Arequipa")

    def _envio_en_destino(self):
        envio = services.crear_envio(dict(
            remitente_nombre="Tienda X", origen_distrito="Miraflores", origen_direccion="Av. Larco 100",
            destinatario_nombre="Ana P", destinatario_telefono="+51900111222",
            destino_distrito="Arequipa", destino_direccion="Av. Independencia 200",
            nivel=Envio.NIVEL_INTERPROVINCIAL, peso_kg=Decimal("10"),
        ))
        for estado in (Envio.ESTADO_ASIGNADO, Envio.ESTADO_RECOGIDO, Envio.ESTADO_EN_RUTA, Envio.ESTADO_EN_DESTINO):
            services.registrar_evento(envio, estado)
        return envio

    def test_asigna_y_pasa_a_en_reparto_destino(self):
        envio = self._envio_en_destino()
        services.asignar_reparto_destino(envio, self.afiliado)
        envio.refresh_from_db()
        self.assertEqual(envio.estado, Envio.ESTADO_EN_REPARTO_DESTINO)
        self.assertEqual(envio.transportista_destino_id, self.afiliado.id)

    def test_solo_se_puede_asignar_en_destino(self):
        envio = services.crear_envio(dict(
            remitente_nombre="Tienda X", origen_distrito="Miraflores", origen_direccion="Av. Larco 100",
            destinatario_nombre="Ana P", destino_distrito="Arequipa", destino_direccion="Av. Independencia 200",
            nivel=Envio.NIVEL_INTERPROVINCIAL, peso_kg=Decimal("10"),
        ))
        with self.assertRaises(ValidationError):
            services.asignar_reparto_destino(envio, self.afiliado)

    def test_despues_de_en_reparto_destino_puede_entregarse(self):
        envio = self._envio_en_destino()
        services.asignar_reparto_destino(envio, self.afiliado)
        services.registrar_evento(envio, Envio.ESTADO_ENTREGADO, recibido_por="Ana P")
        envio.refresh_from_db()
        self.assertEqual(envio.estado, Envio.ESTADO_ENTREGADO)


class RepartoDestinoApiTests(APITestCase):
    def setUp(self):
        TarifaCargaParcial.objects.all().delete()
        _tarifa_arequipa()
        Transportista.objects.create(nombre="Local Arequipa", ubicacion_frecuente="Arequipa")
        Transportista.objects.create(nombre="Local Cusco", ubicacion_frecuente="Cusco")
        for g in ("Despacho",):
            Group.objects.get_or_create(name=g)
        self.user = User.objects.create_user("enc_destb", password="x")
        self.user.groups.add(Group.objects.get(name="Despacho"))
        self.client.force_authenticate(self.user)
        self.envio = services.crear_envio(dict(
            remitente_nombre="Tienda X", origen_distrito="Miraflores", origen_direccion="Av. Larco 100",
            destinatario_nombre="Ana P", destino_distrito="Arequipa", destino_direccion="Av. Independencia 200",
            nivel=Envio.NIVEL_INTERPROVINCIAL, peso_kg=Decimal("10"),
        ))
        for estado in (Envio.ESTADO_ASIGNADO, Envio.ESTADO_RECOGIDO, Envio.ESTADO_EN_RUTA, Envio.ESTADO_EN_DESTINO):
            services.registrar_evento(self.envio, estado)

    def test_lista_solo_los_de_esa_ciudad(self):
        r = self.client.get(f"/api/v2/shipments/{self.envio.codigo}/destination-carriers")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(r.data["carriers"]), 1)
        self.assertEqual(r.data["carriers"][0]["name"], "Local Arequipa")

    def test_asigna_por_api(self):
        carrier = Transportista.objects.get(nombre="Local Arequipa")
        r = self.client.post(
            f"/api/v2/shipments/{self.envio.codigo}/assign-destination", {"carrierId": carrier.id}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["state"], Envio.ESTADO_EN_REPARTO_DESTINO)
        self.assertEqual(r.data["destinationCarrierName"], "Local Arequipa")


class ShipmentApiInterprovincialTests(APITestCase):
    def setUp(self):
        TarifaCargaParcial.objects.all().delete()
        _tarifa_arequipa()
        for g in ("Despacho",):
            Group.objects.get_or_create(name=g)
        self.user = User.objects.create_user("enc_desp", password="x")
        self.user.groups.add(Group.objects.get(name="Despacho"))
        self.client.force_authenticate(self.user)

    def test_quote_endpoint(self):
        r = self.client.get("/api/v2/shipments/quote", {
            "originDistrict": "Lima", "destDistrict": "Arequipa",
            "level": Envio.NIVEL_INTERPROVINCIAL, "weightKg": 10,
        })
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["price"], 50.0)

    def test_zones_endpoint_incluye_interprovincial(self):
        r = self.client.get("/api/v2/shipments/zones")
        self.assertTrue(any(lvl["value"] == Envio.NIVEL_INTERPROVINCIAL for lvl in r.data["levels"]))

    def test_crea_envio_con_punto_de_entrega(self):
        r = self.client.post("/api/v2/shipments/", {
            "senderName": "Tienda X", "originDistrict": "Miraflores", "originAddress": "Av. Larco 100",
            "recipientName": "Ana P", "recipientPhone": "+51900111222",
            "destDistrict": "Arequipa", "destAddress": "Recojo en agencia",
            "destPickupPoint": "Agencia Arequipa Centro",
            "level": Envio.NIVEL_INTERPROVINCIAL, "weightKg": 10,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["recipientFull"]["pickupPoint"], "Agencia Arequipa Centro")
        self.assertEqual(r.data["price"], 50.0)

    def test_crea_envio_con_coordenadas(self):
        r = self.client.post("/api/v2/shipments/", {
            "senderName": "Tienda X", "originDistrict": "Miraflores", "originAddress": "Av. Larco 100",
            "originLat": -12.12, "originLng": -77.03,
            "recipientName": "Ana P", "recipientPhone": "+51900111222",
            "destDistrict": "Arequipa", "destAddress": "Recojo en agencia",
            "destLat": -16.4, "destLng": -71.53,
            "level": Envio.NIVEL_INTERPROVINCIAL, "weightKg": 10,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["sender"]["lat"], -12.12)
        self.assertEqual(r.data["recipientFull"]["lat"], -16.4)


class PuntoEntregaDestinoTests(APITestCase):
    def test_para_ciudad_case_insensitive(self):
        PuntoEntregaDestino.objects.create(ciudad="Arequipa", nombre="Agencia Centro")
        PuntoEntregaDestino.objects.create(ciudad="arequipa", nombre="Agencia Norte", activo=False)
        PuntoEntregaDestino.objects.create(ciudad="Cusco", nombre="Agencia Cusco")
        self.assertEqual(PuntoEntregaDestino.para_ciudad("AREQUIPA").count(), 1)  # la inactiva no cuenta
        self.assertEqual(PuntoEntregaDestino.para_ciudad("").count(), 0)


class PickupPointsApiTests(APITestCase):
    def setUp(self):
        for g in ("Despacho",):
            Group.objects.get_or_create(name=g)
        self.user = User.objects.create_user("enc_pep", password="x")
        self.user.groups.add(Group.objects.get(name="Despacho"))
        self.client.force_authenticate(self.user)

    def test_crud(self):
        r = self.client.post("/api/v2/shipments/pickup-points", {
            "city": "Arequipa", "name": "Agencia Centro", "address": "Calle Mercaderes 100",
            "phone": "+51999888777", "schedule": "Lun-Sáb 9am-7pm",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        pid = r.data["id"]

        r = self.client.get("/api/v2/shipments/pickup-points", {"city": "arequipa"})
        self.assertEqual(len(r.data["points"]), 1)
        self.assertEqual(r.data["points"][0]["name"], "Agencia Centro")

        r = self.client.patch(f"/api/v2/shipments/pickup-points/{pid}", {"active": False}, format="json")
        self.assertFalse(r.data["active"])

        r = self.client.get("/api/v2/shipments/pickup-points", {"city": "arequipa"})
        self.assertEqual(len(r.data["points"]), 0)  # inactivo, no aparece filtrado por ciudad

        self.assertEqual(self.client.delete(f"/api/v2/shipments/pickup-points/{pid}").status_code, 204)

    def test_requiere_ciudad_y_nombre(self):
        r = self.client.post("/api/v2/shipments/pickup-points", {"city": "", "name": "X"}, format="json")
        self.assertEqual(r.status_code, 400)
