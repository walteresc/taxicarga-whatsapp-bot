import datetime
import json

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from apps.campo.models import Conductor, EquipoDia, ProgramacionServicio, Vehiculo
from apps.servicios.models import Servicio


class PizarraMatrixTests(TestCase):
    def setUp(self):
        group, _ = Group.objects.get_or_create(name="Administrador")
        self.user = User.objects.create_user("matrix-admin", password="Admin123*")
        self.user.groups.add(group)
        self.client.login(username="matrix-admin", password="Admin123*")

        self.fecha = datetime.date.today()
        self.vehiculo = Vehiculo.objects.create(
            placa="MAT-001",
            marca="JAC",
            modelo="X200",
            capacidad_toneladas=2,
            activo=True,
        )
        self.conductor = Conductor.objects.create(
            nombre="Conductor Matriz",
            dni="87654321",
            telefono="999111222",
            activo=True,
        )
        self.equipo = EquipoDia.objects.create(
            fecha=self.fecha,
            vehiculo=self.vehiculo,
            conductor=self.conductor,
        )
        self.servicio = Servicio.objects.create(
            codigo="SVC-MATRIX",
            estado="programado",
        )
        self.programacion = ProgramacionServicio.objects.create(
            servicio=self.servicio,
            vehiculo=self.vehiculo,
            conductor=self.conductor,
            fecha=self.fecha,
            hora_inicio=datetime.time(8, 30),
            monto=120,
            estado_operativo=ProgramacionServicio.ESTADO_PROGRAMADO,
        )

    def test_muestra_equipos_en_filas_y_pendientes_en_cabecera(self):
        response = self.client.get(
            reverse("dashboard-pizarra"),
            {"view": "day", "date": self.fecha.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="matrix-team-row"')
        self.assertContains(response, 'class="matrix-hour"')
        self.assertContains(response, 'class="unassigned-card"')
        self.assertContains(response, "SVC-MATRIX")
        self.assertContains(response, "MAT-001 | Conductor Matriz")

    def test_asignar_pendiente_a_equipo_conserva_hora_original(self):
        response = self.client.post(
            reverse("pizarra-programacion-mover"),
            json.dumps({
                "ps_id": self.programacion.pk,
                "equipo_id": self.equipo.pk,
                "fecha": self.fecha.isoformat(),
                "hora": "08:30",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.programacion.refresh_from_db()
        self.assertEqual(self.programacion.equipo_dia, self.equipo)
        self.assertEqual(self.programacion.hora_inicio, datetime.time(8, 30))
