"""Rastreo público unificado (Fase 0, 2026-09): código + teléfono, sin login.
POST /api/v2/track/lookup {code, phone}."""
import datetime
from decimal import Decimal

from django.core.cache import caches
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.campo.models import ProgramacionServicio
from apps.catalogo.models import TipoVehiculo
from apps.clientes.models import Cliente
from apps.encomiendas.models import Envio
from apps.servicios.models import Servicio
from apps.tercerizacion.models import Transportista, TransportistaVehiculo

_NO_THROTTLE = override_settings(REST_FRAMEWORK={
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_RATES": {"tracking_lookup": "1000/hour"},
})


@_NO_THROTTLE
class TrackingLookupShipmentTests(APITestCase):
    def setUp(self):
        caches["throttle"].clear()
        self.envio = Envio.objects.create(
            remitente_nombre="Tienda X", remitente_telefono="+51900111222",
            origen_distrito="Miraflores", origen_direccion="Av. Larco 100",
            destinatario_nombre="Ana P", destinatario_telefono="+51988777666",
            destino_distrito="Los Olivos", destino_direccion="Av. Universitaria 200",
        )

    def test_encuentra_por_telefono_remitente(self):
        r = self.client.post("/api/v2/track/lookup", {"code": self.envio.codigo, "phone": "1222"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["type"], "shipment")
        self.assertEqual(r.data["code"], self.envio.codigo)

    def test_encuentra_por_telefono_destinatario(self):
        r = self.client.post("/api/v2/track/lookup", {"code": self.envio.codigo, "phone": "7666"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_codigo_correcto_telefono_incorrecto_no_encuentra(self):
        r = self.client.post("/api/v2/track/lookup", {"code": self.envio.codigo, "phone": "0000"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_codigo_inexistente_mismo_mensaje_generico(self):
        r1 = self.client.post("/api/v2/track/lookup", {"code": "ENC-99999", "phone": "1222"}, format="json")
        r2 = self.client.post("/api/v2/track/lookup", {"code": self.envio.codigo, "phone": "0000"}, format="json")
        self.assertEqual(r1.status_code, 400)
        self.assertEqual(r1.data["error"], r2.data["error"])  # no delata cuál dato falló

    def test_case_insensitive_en_el_codigo(self):
        r = self.client.post("/api/v2/track/lookup", {"code": self.envio.codigo.lower(), "phone": "1222"}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_telefono_corto_rechazado(self):
        r = self.client.post("/api/v2/track/lookup", {"code": self.envio.codigo, "phone": "12"}, format="json")
        self.assertEqual(r.status_code, 400)


@_NO_THROTTLE
class TrackingLookupCargoTests(APITestCase):
    def setUp(self):
        caches["throttle"].clear()
        self.cliente = Cliente.objects.create(nombre="Juan Pérez", telefono="+51955444333")
        self.servicio = Servicio.objects.create(
            cliente=self.cliente, distrito_origen="Surco", distrito_destino="Ate",
            fecha_servicio=datetime.date(2026, 12, 1), horario_servicio="09:00",
        )

    def test_sin_programacion_devuelve_pendiente(self):
        r = self.client.post("/api/v2/track/lookup", {"code": self.servicio.codigo, "phone": "4333"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["type"], "cargo")
        self.assertEqual(r.data["state"], "pendiente")
        self.assertIsNone(r.data["assignee"])

    def test_con_transportista_tercerizado_expone_placa_y_conductor(self):
        transportista = Transportista.objects.create(nombre="Transportes ABC")
        camion = TipoVehiculo.objects.get(codigo="camion")
        veh = TransportistaVehiculo.objects.create(transportista=transportista, placa="XYZ-123", tipo_vehiculo=camion)
        ProgramacionServicio.objects.create(
            servicio=self.servicio, transportista=transportista, transportista_vehiculo=veh,
            conductor_externo="Pedro Gómez",
            fecha=datetime.date(2026, 12, 1), hora_inicio=datetime.time(9, 0), monto=Decimal("300"),
            estado_operativo=ProgramacionServicio.ESTADO_EN_RUTA,
        )
        r = self.client.post("/api/v2/track/lookup", {"code": self.servicio.codigo, "phone": "4333"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["state"], "en_ruta")
        self.assertEqual(r.data["assignee"]["plate"], "XYZ-123")
        self.assertEqual(r.data["assignee"]["driver"], "Pedro Gómez")
        self.assertEqual(r.data["assignee"]["kind"], "carrier")

    def test_telefono_no_coincide_no_encuentra(self):
        r = self.client.post("/api/v2/track/lookup", {"code": self.servicio.codigo, "phone": "0000"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_codigo_svc_tambien_funciona(self):
        # Servicio sin lead_origen → codigo SVC-NNNN (no CRG-), toma el mismo camino.
        self.assertTrue(self.servicio.codigo.startswith("SVC-"))
        r = self.client.post("/api/v2/track/lookup", {"code": self.servicio.codigo, "phone": "4333"}, format="json")
        self.assertEqual(r.status_code, 200)
