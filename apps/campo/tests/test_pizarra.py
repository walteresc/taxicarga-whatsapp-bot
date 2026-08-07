import json
import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group
from apps.campo.models import ProgramacionServicio, Vehiculo, Conductor, EquipoDia
from apps.servicios.models import Servicio, ESTADOS_SERVICIO


class PizarraTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.groups = {}
        for group_name in ["Administrador", "Supervisor", "Asesor de Ventas", "Conductor", "Ayudante"]:
            group, _ = Group.objects.get_or_create(name=group_name)
            self.groups[group_name] = group

        self.admin = User.objects.create_user("admin", password="Admin123*")
        self.admin.groups.add(self.groups["Administrador"])

        self.supervisor = User.objects.create_user("supervisor", password="Supervisor123*")
        self.supervisor.groups.add(self.groups["Supervisor"])

        self.asesor = User.objects.create_user("demo_vendedor", password="Demo123*")
        self.asesor.groups.add(self.groups["Asesor de Ventas"])

        self.conductor_user = User.objects.create_user("conductor_demo", password="Conductor123*")
        self.conductor_user.groups.add(self.groups["Conductor"])

        self.ayudante_user = User.objects.create_user("ayudante_demo", password="Ayudante123*")
        self.ayudante_user.groups.add(self.groups["Ayudante"])

        # Create vehiculo + conductor for programacion
        self.vehiculo = Vehiculo.objects.create(
            placa="ABC-123", marca="Toyota", modelo="Hilux",
            capacidad_toneladas=1.5, activo=True,
        )
        self.conductor = Conductor.objects.create(
            nombre="Carlos Perez", dni="12345678", telefono="999888777",
            activo=True, usuario=self.conductor_user,
        )

        today = datetime.date.today()

        # Create servicios with different estados
        self.servicio_pendiente = Servicio.objects.create(
            codigo="SVC-0001", estado="pendiente",
        )
        self.servicio_programado = Servicio.objects.create(
            codigo="SVC-0002", estado="programado",
        )
        self.servicio_en_ruta = Servicio.objects.create(
            codigo="SVC-0003", estado="en_ruta",
        )
        self.servicio_finalizado = Servicio.objects.create(
            codigo="SVC-0004", estado="finalizado",
        )
        self.servicio_cancelado = Servicio.objects.create(
            codigo="SVC-0005", estado="cancelado",
        )

        # Create ProgramacionServicio for each
        self.prog_pendiente = ProgramacionServicio.objects.create(
            servicio=self.servicio_pendiente, fecha=today,
            vehiculo=self.vehiculo, conductor=self.conductor,
            hora_inicio=datetime.time(8, 0), monto=100,
            estado_operativo="programado",
        )
        self.prog_programado = ProgramacionServicio.objects.create(
            servicio=self.servicio_programado, fecha=today,
            vehiculo=self.vehiculo, conductor=self.conductor,
            hora_inicio=datetime.time(9, 0), monto=200,
            estado_operativo="programado",
        )
        self.prog_en_ruta = ProgramacionServicio.objects.create(
            servicio=self.servicio_en_ruta, fecha=today,
            vehiculo=self.vehiculo, conductor=self.conductor,
            hora_inicio=datetime.time(10, 0), monto=300,
            estado_operativo="en_ruta",
        )
        self.prog_finalizado = ProgramacionServicio.objects.create(
            servicio=self.servicio_finalizado, fecha=today,
            vehiculo=self.vehiculo, conductor=self.conductor,
            hora_inicio=datetime.time(11, 0), monto=400,
            estado_operativo="finalizado",
        )
        self.prog_cancelado = ProgramacionServicio.objects.create(
            servicio=self.servicio_cancelado, fecha=today,
            vehiculo=self.vehiculo, conductor=self.conductor,
            hora_inicio=datetime.time(12, 0), monto=500,
            estado_operativo="cancelado",
        )

    def login_user(self, username, password):
        login = self.client.login(username=username, password=password)
        self.assertTrue(login)

    def test_pizarra_carga_200(self):
        self.login_user("admin", "Admin123*")
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertEqual(response.status_code, 200)

    def test_pizarra_muestra_6_columnas_estado(self):
        self.login_user("admin", "Admin123*")
        response = self.client.get(reverse("dashboard-pizarra"))
        for _, label in ESTADOS_SERVICIO:
            self.assertContains(response, label)

    def test_pizarra_muestra_servicios_por_estado(self):
        self.login_user("admin", "Admin123*")
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertContains(response, "SVC-0001")
        self.assertContains(response, "SVC-0002")
        self.assertContains(response, "SVC-0003")
        self.assertContains(response, "SVC-0004")
        self.assertContains(response, "SVC-0005")

    def test_pizarra_navegacion_semanal(self):
        self.login_user("admin", "Admin123*")
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertContains(response, "Semana anterior")
        self.assertContains(response, "Semana siguiente")
        self.assertContains(response, "Semana actual")

    def test_api_cambiar_estado_pendiente_a_programado(self):
        self.login_user("admin", "Admin123*")
        url = reverse("api-cambiar-estado")
        response = self.client.post(
            url,
            json.dumps({"pk": self.prog_pendiente.pk, "estado": "programado"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["servicio_estado"], "programado")

        # Verify DB updated
        self.servicio_pendiente.refresh_from_db()
        self.assertEqual(self.servicio_pendiente.estado, "programado")
        self.prog_pendiente.refresh_from_db()
        self.assertEqual(self.prog_pendiente.estado_operativo, "programado")

    def test_api_cambiar_estado_a_cancelado(self):
        self.login_user("admin", "Admin123*")
        url = reverse("api-cambiar-estado")
        response = self.client.post(
            url,
            json.dumps({"pk": self.prog_en_ruta.pk, "estado": "cancelado"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["servicio_estado"], "cancelado")

        self.servicio_en_ruta.refresh_from_db()
        self.assertEqual(self.servicio_en_ruta.estado, "cancelado")
        self.prog_en_ruta.refresh_from_db()
        self.assertEqual(self.prog_en_ruta.estado_operativo, "cancelado")

    def test_api_cambiar_estado_invalido(self):
        self.login_user("admin", "Admin123*")
        url = reverse("api-cambiar-estado")
        response = self.client.post(
            url,
            json.dumps({"pk": self.prog_pendiente.pk, "estado": "inexistente"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_api_sin_autenticacion_redirecciona(self):
        url = reverse("api-cambiar-estado")
        response = self.client.post(
            url,
            json.dumps({"pk": 1, "estado": "programado"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)

    def test_permiso_administrador(self):
        self.login_user("admin", "Admin123*")
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertEqual(response.status_code, 200)

    def test_permiso_supervisor(self):
        self.login_user("supervisor", "Supervisor123*")
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertEqual(response.status_code, 200)

    def test_permiso_asesor(self):
        self.login_user("demo_vendedor", "Demo123*")
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertEqual(response.status_code, 200)

    def test_permiso_conductor(self):
        self.login_user("conductor_demo", "Conductor123*")
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertEqual(response.status_code, 200)

    def test_permiso_ayudante(self):
        self.login_user("ayudante_demo", "Ayudante123*")
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertEqual(response.status_code, 200)

    def test_sidebar_menus_por_rol(self):
        for user, expected_menus in [
            ("admin", ["Leads", "Servicios", "Pizarra", "Gestión de Campo", "Bot WhatsApp", "Canales WhatsApp", "Reportes"]),
            ("supervisor", ["Leads", "Servicios", "Pizarra", "Gestión de Campo", "Bot WhatsApp", "Canales WhatsApp", "Reportes"]),
            ("demo_vendedor", ["Leads", "Servicios", "Pizarra", "Gestión de Campo", "Bot WhatsApp", "Canales WhatsApp"]),
            ("conductor_demo", ["Mis Servicios", "Mi Programación"]),
            ("ayudante_demo", ["Mis Servicios", "Mi Programación"]),
        ]:
            self.login_user(user, "Admin123*" if user == "admin" else "Supervisor123*" if user == "supervisor" else "Demo123*" if user == "demo_vendedor" else "Conductor123*" if user == "conductor_demo" else "Ayudante123*")
            response = self.client.get(reverse("dashboard-home"), follow=True)
            self.assertEqual(response.status_code, 200)

    def test_seguridad_redireccion_sin_login(self):
        response = self.client.get(reverse("dashboard-pizarra"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard/login/", response.url)

    def test_seguridad_no_acceso_campo_conductor_ayudante(self):
        self.login_user("conductor_demo", "Conductor123*")
        response = self.client.get(reverse("dashboard-campo"))
        self.assertEqual(response.status_code, 302)

        self.login_user("ayudante_demo", "Ayudante123*")
        response = self.client.get(reverse("dashboard-campo"))
        self.assertEqual(response.status_code, 302)
