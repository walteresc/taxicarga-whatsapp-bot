import datetime
import json
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from apps.campo.models import Conductor, EquipoDia, ProgramacionServicio, Vehiculo
from apps.clientes.models import Cliente
from apps.servicios.models import SERVICIO_ASIGNADO, Servicio


class PizarraServiciosSinAsignarTests(TestCase):
    def setUp(self):
        group, _ = Group.objects.get_or_create(name="Administrador")
        self.user = User.objects.create_user("sin-asignar", password="Admin123*")
        self.user.groups.add(group)
        self.client.login(username="sin-asignar", password="Admin123*")
        self.fecha = datetime.date(2026, 6, 14)
        self.cliente = Cliente.objects.create(
            nombre="Cliente pendiente",
            telefono="900000014",
        )
        self.servicio = Servicio.objects.create(
            cliente=self.cliente,
            estado="programado",
            fecha_servicio=self.fecha,
            horario_servicio="08:30",
            precio=Decimal("120.00"),
        )
        self.vehiculo = Vehiculo.objects.create(
            placa="PEN-014",
            marca="JAC",
            modelo="X200",
            capacidad_toneladas=2,
        )
        self.conductor = Conductor.objects.create(
            nombre="Conductor pendiente",
            dni="14062026",
            telefono="999000014",
        )
        self.equipo = EquipoDia.objects.create(
            fecha=self.fecha,
            vehiculo=self.vehiculo,
            conductor=self.conductor,
        )

    def test_muestra_servicio_sin_programacion_con_edicion_y_combo(self):
        response = self.client.get(
            reverse("dashboard-pizarra"),
            {"view": "day", "date": self.fecha.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.servicio.codigo)
        self.assertContains(response, "Cliente pendiente")
        self.assertContains(
            response,
            reverse("dashboard-servicios-edit", args=[self.servicio.pk]),
        )
        self.assertContains(
            response,
            f'data-servicio-id="{self.servicio.pk}"',
        )
        self.assertContains(response, "PEN-014 | Conductor pendiente")

    def test_combo_asigna_servicio_al_equipo(self):
        response = self.client.post(
            reverse("pizarra-programacion-asignar"),
            json.dumps({
                "servicio_id": self.servicio.pk,
                "equipo_id": self.equipo.pk,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        programacion = ProgramacionServicio.objects.get(servicio=self.servicio)
        self.assertEqual(programacion.equipo_dia, self.equipo)
        self.assertEqual(programacion.fecha, self.fecha)
        self.assertEqual(programacion.hora_inicio, datetime.time(8, 30))
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.estado, SERVICIO_ASIGNADO)
