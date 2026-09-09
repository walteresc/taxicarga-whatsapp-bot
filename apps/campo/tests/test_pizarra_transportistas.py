"""Fase 2b — vehículos de transportistas externos como filas de la Pizarra v2."""
import datetime
import json
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.campo.models import FilaPizarraTransportista, ProgramacionServicio, Vehiculo
from apps.catalogo.models import TipoVehiculo
from apps.clientes.models import Cliente
from apps.servicios.models import Servicio
from apps.tercerizacion.models import Transportista, TransportistaVehiculo


class PizarraTransportistasTests(TestCase):
    def setUp(self):
        group, _ = Group.objects.get_or_create(name="Administrador")
        self.user = User.objects.create_user("pz-terc", password="Admin123*")
        self.user.groups.add(group)
        self.client.login(username="pz-terc", password="Admin123*")

        self.fecha = datetime.date(2026, 9, 20)
        self.cliente = Cliente.objects.create(nombre="Cliente 2b", telefono="900000020")
        self.tipo = TipoVehiculo.objects.create(codigo="furgon", nombre="Furgón")
        self.carrier = Transportista.objects.create(nombre="Transportes Sur SAC", documento="20111111111")
        self.tv = TransportistaVehiculo.objects.create(
            transportista=self.carrier, placa="TSR-101", tipo_vehiculo=self.tipo,
            marca="Hyundai", modelo="HD65",
        )

    # helpers -------------------------------------------------------------
    def _servicio(self, hora="09:00", precio="300.00"):
        return Servicio.objects.create(
            cliente=self.cliente, estado="programado",
            fecha_servicio=self.fecha, horario_servicio=hora, precio=Decimal(precio),
        )

    def _post(self, action, body):
        return self.client.post(
            reverse("v2-pizarra-action", args=[action]),
            data=json.dumps(body), content_type="application/json",
        )

    def _board(self):
        r = self.client.get(reverse("v2-pizarra"), {"date": self.fecha.isoformat()})
        self.assertEqual(r.status_code, 200)
        return r.json()

    # tests -------------------------------------------------------------
    def test_add_carrier_row_aparece_en_el_tablero(self):
        r = self._post("add-carrier-row", {
            "date": self.fecha.isoformat(), "carrierVehicleId": self.tv.id, "driverName": "Juan Pérez",
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["resourceId"], f"t{self.tv.id}")

        row = next(x for x in self._board()["resources"] if x["id"] == f"t{self.tv.id}")
        self.assertEqual(row["kind"], "tercerizado")
        self.assertEqual(row["label"], "TSR-101")
        self.assertEqual(row["driverName"], "Juan Pérez")

    def test_add_carrier_row_idempotente_actualiza_conductor(self):
        self._post("add-carrier-row", {"date": self.fecha.isoformat(), "carrierVehicleId": self.tv.id})
        self._post("add-carrier-row", {
            "date": self.fecha.isoformat(), "carrierVehicleId": self.tv.id, "driverName": "Otro Chofer",
        })
        self.assertEqual(FilaPizarraTransportista.objects.filter(fecha=self.fecha).count(), 1)
        self.assertEqual(
            FilaPizarraTransportista.objects.get(fecha=self.fecha).conductor_externo, "Otro Chofer",
        )

    def test_assign_a_transportista_crea_prog_y_flipea_modalidad(self):
        self._post("add-carrier-row", {
            "date": self.fecha.isoformat(), "carrierVehicleId": self.tv.id, "driverName": "Chofer Fila",
        })
        s = self._servicio()
        r = self._post("assign", {"serviceId": s.id, "resourceId": f"t{self.tv.id}", "start": "09:00"})
        self.assertEqual(r.status_code, 200)

        ps = ProgramacionServicio.objects.get(servicio=s)
        self.assertIsNone(ps.vehiculo_id)
        self.assertEqual(ps.transportista_vehiculo_id, self.tv.id)
        self.assertEqual(ps.transportista_id, self.carrier.id)
        self.assertEqual(ps.conductor_externo, "Chofer Fila")
        s.refresh_from_db()
        self.assertEqual(s.modalidad_ejecucion, Servicio.MODALIDAD_TERCERIZADO)

        board = self._board()
        a = next(x for x in board["assignments"] if x["serviceId"] == s.id)
        self.assertEqual(a["resourceId"], f"t{self.tv.id}")
        self.assertEqual(a["mode"], "tercerizado")
        self.assertEqual(a["driverName"], "Chofer Fila")

    def test_conflicto_de_horario_en_el_mismo_transportista(self):
        self._post("add-carrier-row", {"date": self.fecha.isoformat(), "carrierVehicleId": self.tv.id})
        s1 = self._servicio(hora="09:00")
        s2 = self._servicio(hora="09:30")
        self._post("assign", {"serviceId": s1.id, "resourceId": f"t{self.tv.id}", "start": "09:00", "end": "11:00"})
        r = self._post("assign", {"serviceId": s2.id, "resourceId": f"t{self.tv.id}", "start": "09:30", "end": "10:30"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("Choca", r.json()["error"])

    def test_remove_carrier_row_bloqueada_si_tiene_servicio(self):
        self._post("add-carrier-row", {"date": self.fecha.isoformat(), "carrierVehicleId": self.tv.id})
        s = self._servicio()
        self._post("assign", {"serviceId": s.id, "resourceId": f"t{self.tv.id}", "start": "09:00"})
        r = self._post("remove-carrier-row", {"date": self.fecha.isoformat(), "resourceId": f"t{self.tv.id}"})
        self.assertEqual(r.status_code, 409)
        self.assertTrue(FilaPizarraTransportista.objects.filter(fecha=self.fecha).exists())

    def test_unassign_y_luego_remove_carrier_row(self):
        self._post("add-carrier-row", {"date": self.fecha.isoformat(), "carrierVehicleId": self.tv.id})
        s = self._servicio()
        self._post("assign", {"serviceId": s.id, "resourceId": f"t{self.tv.id}", "start": "09:00"})
        ps = ProgramacionServicio.objects.get(servicio=s)
        self._post("unassign", {"assignmentId": ps.id})
        r = self._post("remove-carrier-row", {"date": self.fecha.isoformat(), "resourceId": f"t{self.tv.id}"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(any(x["id"] == f"t{self.tv.id}" for x in self._board()["resources"]))

    def test_move_propio_a_transportista_y_vuelta(self):
        veh = Vehiculo.objects.create(placa="OWN-1", marca="JAC", modelo="X", capacidad_toneladas=3)
        s = self._servicio()
        self._post("assign", {"serviceId": s.id, "resourceId": f"v{veh.id}", "start": "09:00"})
        ps = ProgramacionServicio.objects.get(servicio=s)

        self._post("add-carrier-row", {"date": self.fecha.isoformat(), "carrierVehicleId": self.tv.id})
        r = self._post("move", {"assignmentId": ps.id, "resourceId": f"t{self.tv.id}", "start": "09:00"})
        self.assertEqual(r.status_code, 200)
        ps.refresh_from_db(); s.refresh_from_db()
        self.assertIsNone(ps.vehiculo_id)
        self.assertEqual(ps.transportista_vehiculo_id, self.tv.id)
        self.assertIsNone(ps.conductor_id)
        self.assertEqual(s.modalidad_ejecucion, Servicio.MODALIDAD_TERCERIZADO)

        r = self._post("move", {"assignmentId": ps.id, "resourceId": f"v{veh.id}", "start": "09:00"})
        self.assertEqual(r.status_code, 200)
        ps.refresh_from_db(); s.refresh_from_db()
        self.assertEqual(ps.vehiculo_id, veh.id)
        self.assertIsNone(ps.transportista_vehiculo_id)
        self.assertEqual(ps.conductor_externo, "")
        self.assertEqual(s.modalidad_ejecucion, Servicio.MODALIDAD_PROPIO)

    def test_constraint_xor_vehiculo_transportista(self):
        s = self._servicio()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProgramacionServicio.objects.create(
                    servicio=s, vehiculo=None, transportista_vehiculo=None,
                    fecha=self.fecha, hora_inicio=datetime.time(9, 0), monto=Decimal("10"),
                )
        veh = Vehiculo.objects.create(placa="OWN-9", marca="J", modelo="X", capacidad_toneladas=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProgramacionServicio.objects.create(
                    servicio=s, vehiculo=veh, transportista_vehiculo=self.tv,
                    fecha=self.fecha, hora_inicio=datetime.time(9, 0), monto=Decimal("10"),
                )
