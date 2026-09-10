"""Encomiendas P1: cotización por zona, alta, ciclo de estados, seguimiento."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.catalogo.models import TipoVehiculo
from apps.encomiendas import services
from apps.encomiendas.models import (
    ConfiguracionEncomiendas, Envio, RendicionCaja, RutaReparto, TarifaZona, ZonaReparto,
)
from apps.tercerizacion.models import Transportista, TransportistaVehiculo

User = get_user_model()


def _seed():
    if not ZonaReparto.objects.exists():
        call_command("seed_encomiendas")


BASE = dict(
    remitente_nombre="Tienda X", origen_distrito="Miraflores", origen_direccion="Av. Larco 100",
    destinatario_nombre="Ana P", destinatario_telefono="+51900111222",
    destino_distrito="Los Olivos", destino_direccion="Av. Universitaria 200",
    peso_kg=Decimal("3"),
)


class CotizacionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        _seed()

    def test_cotiza_por_zona(self):
        r = services.cotizar(origen_distrito="Miraflores", destino_distrito="Surco",
                             nivel=Envio.NIVEL_EXPRESS, peso_kg=2)
        self.assertEqual(r["zoneFrom"], "Lima Moderna")
        self.assertEqual(r["zoneTo"], "Lima Moderna")
        self.assertEqual(r["price"], 12.0)  # local express

    def test_peso_extra_suma(self):
        r = services.cotizar(origen_distrito="Miraflores", destino_distrito="Miraflores",
                             nivel=Envio.NIVEL_EXPRESS, peso_kg=8)  # 5 incluidos + 3 * 1.5
        self.assertEqual(r["price"], 12.0 + 4.5)

    def test_sin_cobertura(self):
        with self.assertRaises(ValidationError):
            services.cotizar(origen_distrito="Cusco", destino_distrito="Miraflores")


class CicloEnvioTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        _seed()

    def _carrier(self):
        c = Transportista.objects.create(nombre="Moto Uno")
        v = TransportistaVehiculo.objects.create(
            transportista=c, placa="MOT-1", tipo_vehiculo=TipoVehiculo.objects.get(codigo="camion"))
        return c, v

    def test_alta_cotiza_sola_y_registra_evento(self):
        e = services.crear_envio(dict(BASE))
        self.assertTrue(e.codigo.startswith("ENC-"))
        self.assertGreater(e.precio, 0)
        self.assertEqual(e.estado, Envio.ESTADO_REGISTRADO)
        self.assertEqual(e.eventos.count(), 1)

    def test_flujo_completo(self):
        c, v = self._carrier()
        e = services.crear_envio(dict(BASE))
        services.asignar_envio(e, c, vehiculo=v)
        services.registrar_evento(e, Envio.ESTADO_RECOGIDO)
        services.registrar_evento(e, Envio.ESTADO_EN_RUTA)
        services.registrar_evento(e, Envio.ESTADO_ENTREGADO, recibido_por="Ana P")
        e.refresh_from_db()
        self.assertEqual(e.estado, Envio.ESTADO_ENTREGADO)
        self.assertEqual(e.recibido_por, "Ana P")
        self.assertIsNotNone(e.entregado_en)
        self.assertEqual(e.eventos.count(), 5)  # registrado, asignado, recogido, en_ruta, entregado

    def test_transicion_invalida(self):
        e = services.crear_envio(dict(BASE))
        with self.assertRaises(ValidationError):
            services.registrar_evento(e, Envio.ESTADO_ENTREGADO)  # sin recoger

    def test_cancelar_solo_antes_de_recoger(self):
        c, v = self._carrier()
        e = services.crear_envio(dict(BASE))
        services.asignar_envio(e, c, vehiculo=v)
        services.registrar_evento(e, Envio.ESTADO_RECOGIDO)
        with self.assertRaises(ValidationError):
            services.cancelar_envio(e)

    def test_contraentrega_exige_monto(self):
        with self.assertRaises(ValidationError):
            services.crear_envio(dict(BASE, es_contraentrega=True))


class ApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        _seed()

    def setUp(self):
        Group.objects.get_or_create(name="Despacho")
        Group.objects.get_or_create(name="Transportista")
        self.op = User.objects.create_user("enc_op", password="x")
        self.op.groups.add(Group.objects.get(name="Despacho"))

    def test_crear_y_listar(self):
        self.client.force_authenticate(self.op)
        r = self.client.post("/api/v2/shipments/", {
            "senderName": "T", "originDistrict": "Miraflores", "originAddress": "Av. Larco 1",
            "recipientName": "A", "destDistrict": "Callao", "destAddress": "Av. Saenz 2",
            "weightKg": 2, "level": "express",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        code = r.data["code"]
        self.assertGreater(r.data["price"], 0)
        r = self.client.get("/api/v2/shipments/")
        self.assertEqual(len(r.data["results"]), 1)
        r = self.client.get(f"/api/v2/shipments/{code}/")
        self.assertEqual(len(r.data["events"]), 1)

    def test_quote_endpoint(self):
        self.client.force_authenticate(self.op)
        r = self.client.get("/api/v2/shipments/quote", {"originDistrict": "Ate", "destDistrict": "Ate", "weightKg": 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["price"], 12.0)

    def test_portal_transportista_ve_y_marca(self):
        carrier = Transportista.objects.create(nombre="Moto Portal")
        cu = User.objects.create_user("enc_carrier", password="x")
        cu.groups.add(Group.objects.get(name="Transportista"))
        carrier.usuario = cu
        carrier.save()
        e = services.crear_envio(dict(BASE))
        services.asignar_envio(e, carrier)

        self.client.force_authenticate(cu)
        r = self.client.get("/api/v2/portal/carrier/deliveries")
        self.assertEqual(len(r.data["results"]), 1)
        r = self.client.post(f"/api/v2/portal/carrier/deliveries/{e.codigo}/event", {"state": "recogido"}, format="json")
        self.assertEqual(r.status_code, 200)
        e.refresh_from_db()
        self.assertEqual(e.estado, Envio.ESTADO_RECOGIDO)

    def test_cod_flow_api(self):
        ConfiguracionEncomiendas.objects.filter(pk=1).delete()
        Group.objects.get_or_create(name="Finanzas")
        Group.objects.get_or_create(name="Transportista")
        fin = User.objects.create_user("cod_fin", password="x")
        fin.groups.add(Group.objects.get(name="Finanzas"))
        carrier = Transportista.objects.create(nombre="Moto COD")
        cu = User.objects.create_user("cod_carrier", password="x")
        cu.groups.add(Group.objects.get(name="Transportista"))
        carrier.usuario = cu
        carrier.save()
        e = services.crear_envio(dict(BASE, es_contraentrega=True, monto_contraentrega=Decimal("80"), precio=Decimal("10")))
        services.asignar_envio(e, carrier)
        services.registrar_evento(e, Envio.ESTADO_EN_RUTA)

        self.client.force_authenticate(cu)
        r = self.client.post(f"/api/v2/portal/carrier/deliveries/{e.codigo}/event",
                             {"state": "entregado", "receivedBy": "Ana", "codCollected": "80", "codMethod": "yape"},
                             format="multipart")
        self.assertEqual(r.status_code, 200, r.data)

        self.client.force_authenticate(fin)
        r = self.client.get("/api/v2/cod/pending")
        self.assertEqual(r.data["groups"][0]["total"], 80.0)
        r = self.client.post("/api/v2/cod/settlements", {"carrierId": carrier.id}, format="json")
        code = r.data["code"]
        r = self.client.post(f"/api/v2/cod/settlements/{code}", {"amount": "80", "reference": "yape-ok"}, format="json")
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/v2/cod/to-remit")
        self.assertEqual(len(r.data["groups"]), 1)

    def test_track_publico_sin_sesion(self):
        e = services.crear_envio(dict(BASE))
        r = self.client.get(f"/api/v2/track/{e.token}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["code"], e.codigo)
        self.assertNotIn("recipientPhone", r.data)
        self.assertIn("events", r.data)

    def test_asesor_de_ventas_puede_crear_pero_transportista_no(self):
        Group.objects.get_or_create(name="Asesor de Ventas")
        ase = User.objects.create_user("enc_ase", password="x")
        ase.groups.add(Group.objects.get(name="Asesor de Ventas"))
        self.client.force_authenticate(ase)
        self.assertEqual(self.client.get("/api/v2/shipments/").status_code, 200)


class RutaTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        _seed()

    def _carrier(self):
        c = Transportista.objects.create(nombre=f"Moto {Transportista.objects.count()}")
        return c

    def test_crear_ruta_ordena_por_zona(self):
        c = self._carrier()
        from datetime import date
        e1 = services.crear_envio(dict(BASE, destino_distrito="Los Olivos"))   # Lima Norte (orden 2)
        e2 = services.crear_envio(dict(BASE, destino_distrito="Miraflores"))   # Lima Moderna (orden 1)
        r = services.crear_ruta(transportista=c, fecha=date.today(), envios=[e1, e2])
        codes = list(r.paradas.order_by("orden_ruta").values_list("codigo", flat=True))
        self.assertEqual(codes, [e2.codigo, e1.codigo])  # Moderna antes que Norte
        e1.refresh_from_db()
        self.assertEqual(e1.estado, Envio.ESTADO_ASIGNADO)
        self.assertEqual(e1.transportista_id, c.id)

    def test_iniciar_y_completar_cierra_ruta(self):
        from datetime import date
        c = self._carrier()
        e = services.crear_envio(dict(BASE))
        r = services.crear_ruta(transportista=c, fecha=date.today(), envios=[e])
        services.iniciar_ruta(r)
        r.refresh_from_db()
        self.assertEqual(r.estado, RutaReparto.ESTADO_EN_CURSO)
        e.refresh_from_db()
        self.assertEqual(e.estado, Envio.ESTADO_EN_RUTA)
        services.registrar_evento(e, Envio.ESTADO_ENTREGADO, recibido_por="X")
        r.refresh_from_db()
        self.assertEqual(r.estado, RutaReparto.ESTADO_CERRADA)  # se auto-cerró

    def test_cerrar_ruta_devuelve_pendientes(self):
        from datetime import date
        c = self._carrier()
        e = services.crear_envio(dict(BASE))
        r = services.crear_ruta(transportista=c, fecha=date.today(), envios=[e])
        services.iniciar_ruta(r)
        services.cerrar_ruta(r)
        e.refresh_from_db()
        self.assertEqual(e.estado, Envio.ESTADO_DEVUELTO)

    def test_fallo_incrementa_intentos(self):
        from datetime import date
        c = self._carrier()
        e = services.crear_envio(dict(BASE))
        services.asignar_envio(e, c)
        services.registrar_evento(e, Envio.ESTADO_EN_RUTA)
        services.registrar_evento(e, Envio.ESTADO_FALLIDO, motivo_fallo="nadie en casa")
        e.refresh_from_db()
        self.assertEqual(e.intentos_entrega, 1)
        self.assertEqual(e.estado, Envio.ESTADO_FALLIDO)

    def test_cod_calcula_a_remitir_y_bloquea_sin_monto(self):
        from datetime import date
        ConfiguracionEncomiendas.objects.filter(pk=1).delete()
        c = self._carrier()
        e = services.crear_envio(dict(BASE, es_contraentrega=True, monto_contraentrega=Decimal("120"), precio=Decimal("15")))
        services.asignar_envio(e, c)
        services.registrar_evento(e, Envio.ESTADO_EN_RUTA)
        with self.assertRaises(ValidationError):
            services.registrar_evento(e, Envio.ESTADO_ENTREGADO, recibido_por="X", cod_cobrado=0)
        services.registrar_evento(e, Envio.ESTADO_ENTREGADO, recibido_por="X",
                                  cod_cobrado=Decimal("120"), cod_medio="efectivo")
        e.refresh_from_db()
        # 120 - 3% (3.60) - envío 15 = 101.40
        self.assertEqual(e.cod_cobrado, Decimal("120"))
        self.assertEqual(e.cod_a_remitir, Decimal("101.40"))

    def test_rendicion_de_caja(self):
        from datetime import date
        ConfiguracionEncomiendas.objects.filter(pk=1).delete()
        c = self._carrier()
        e = services.crear_envio(dict(BASE, es_contraentrega=True, monto_contraentrega=Decimal("100"), precio=Decimal("10")))
        services.asignar_envio(e, c)
        services.registrar_evento(e, Envio.ESTADO_EN_RUTA)
        services.registrar_evento(e, Envio.ESTADO_ENTREGADO, recibido_por="X", cod_cobrado=Decimal("100"))

        self.assertEqual(services.cod_por_rendir(c).count(), 1)
        r = services.crear_rendicion(c)
        self.assertEqual(r.esperado, Decimal("100"))
        services.conciliar_rendicion(r, entregado=Decimal("100"), referencia="dep-1")
        r.refresh_from_db()
        self.assertEqual(r.estado, RendicionCaja.ESTADO_CONCILIADA)
        self.assertEqual(r.diferencia, Decimal("0"))
        e.refresh_from_db()
        self.assertTrue(e.cod_rendido)
        # ahora aparece por remitir
        self.assertEqual(services.cod_por_remitir().count(), 1)

    def test_portal_ruta_y_pod(self):
        from datetime import date

        from django.core.files.uploadedfile import SimpleUploadedFile
        Group.objects.get_or_create(name="Transportista")
        c = self._carrier()
        cu = User.objects.create_user("ruta_carrier", password="x")
        cu.groups.add(Group.objects.get(name="Transportista"))
        c.usuario = cu
        c.save()
        e = services.crear_envio(dict(BASE))
        r = services.crear_ruta(transportista=c, fecha=date.today(), envios=[e])

        self.client.force_authenticate(cu)
        resp = self.client.get("/api/v2/portal/carrier/route")
        self.assertEqual(resp.data["route"]["code"], r.codigo)
        self.assertEqual(len(resp.data["route"]["stops"]), 1)

        self.client.post("/api/v2/portal/carrier/route")  # iniciar
        foto = SimpleUploadedFile("pod.jpg", b"fakejpeg", content_type="image/jpeg")
        resp = self.client.post(
            f"/api/v2/portal/carrier/deliveries/{e.codigo}/event",
            {"state": "entregado", "receivedBy": "Ana", "photo": foto}, format="multipart",
        )
        self.assertEqual(resp.status_code, 200)
        e.refresh_from_db()
        self.assertEqual(e.estado, Envio.ESTADO_ENTREGADO)
        self.assertTrue(e.prueba_foto)
