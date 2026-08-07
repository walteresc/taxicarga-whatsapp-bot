import datetime
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.campo.models import Conductor, ProgramacionServicio, Vehiculo
from apps.servicios.models import PagoReserva, Servicio


class PizarraDashboardTests(TestCase):
    def setUp(self):
        group, _ = Group.objects.get_or_create(name="Administrador")
        self.user = User.objects.create_user("pizarra_kpi", password="Admin123*")
        self.user.groups.add(group)
        self.client.login(username="pizarra_kpi", password="Admin123*")

        self.fecha = datetime.date(2026, 6, 13)
        self.vehiculo = Vehiculo.objects.create(
            placa="KPI-101",
            marca="Toyota",
            modelo="Dyna",
            capacidad_toneladas=Decimal("2.50"),
        )
        self.conductor = Conductor.objects.create(
            nombre="Conductor KPI",
            dni="74125896",
            telefono="999111222",
        )
        self.servicio = Servicio.objects.create(
            estado="programado",
            precio=Decimal("500.00"),
        )
        ProgramacionServicio.objects.create(
            servicio=self.servicio,
            vehiculo=self.vehiculo,
            conductor=self.conductor,
            fecha=self.fecha,
            hora_inicio=datetime.time(9, 0),
            monto=Decimal("500.00"),
        )
        PagoReserva.objects.create(
            servicio=self.servicio,
            concepto="adelanto",
            metodo_pago="yape",
            monto=Decimal("150.00"),
            fecha_pago=timezone.now(),
        )
        PagoReserva.objects.create(
            servicio=self.servicio,
            concepto="descuento",
            metodo_pago="otro",
            monto=Decimal("50.00"),
            fecha_pago=timezone.now(),
        )

    def test_vista_dia_muestra_un_dia_y_metricas_del_periodo(self):
        response = self.client.get(
            reverse("dashboard-pizarra"),
            {"view": "day", "date": "2026-06-13"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["dias_data"]), 1)
        self.assertEqual(response.context["total_reservas"], 1)
        self.assertEqual(response.context["monto_total"], Decimal("500.00"))
        self.assertEqual(response.context["cobrado_total"], Decimal("150.00"))
        self.assertEqual(response.context["saldo_total"], Decimal("300.00"))
        self.assertContains(response, "Día anterior")
        self.assertContains(response, "Día siguiente")

    def test_parametro_view_week_ignorado_retorna_un_dia(self):
        response = self.client.get(
            reverse("dashboard-pizarra"),
            {"view": "week", "date": "2026-06-13"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["dias_data"]), 1)
        self.assertContains(response, 'id="pizarra-date-picker"')
        self.assertContains(response, "Monto total")
        self.assertContains(response, "Cobrado")
        self.assertContains(response, "Saldo total")

    def test_reserva_cancelada_no_afecta_metricas(self):
        cancelada = Servicio.objects.create(
            estado="cancelado",
            precio=Decimal("900.00"),
        )
        ProgramacionServicio.objects.create(
            servicio=cancelada,
            vehiculo=self.vehiculo,
            conductor=self.conductor,
            fecha=self.fecha,
            hora_inicio=datetime.time(12, 0),
            monto=Decimal("900.00"),
        )

        response = self.client.get(
            reverse("dashboard-pizarra"),
            {"view": "day", "date": "2026-06-13"},
        )

        self.assertEqual(response.context["total_reservas"], 1)
        self.assertEqual(response.context["monto_total"], Decimal("500.00"))
