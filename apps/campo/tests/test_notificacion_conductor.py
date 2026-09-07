"""Al asignar un conductor a una reserva (Pizarra), el sistema le manda el
detalle del servicio a su WhatsApp real — mismo circuito que usa la bandeja
(Cliente/Lead/Conversación), no un canal aparte. Si la ventana de 24h de
WhatsApp está cerrada, no se intenta enviar: se le devuelve el texto armado
al asesor para que lo mande a mano por WhatsApp Web."""
import datetime
import json
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.utils import timezone

from apps.campo.models import Conductor, EquipoDia, ProgramacionServicio, Vehiculo
from apps.campo.services_notificacion import notificar_conductor_asignacion
from apps.clientes.models import Cliente
from apps.servicios.models import Servicio
from apps.whatsapp.domain import crear_conversacion_manual
from apps.whatsapp.models import WhatsAppChannel


class NotificarConductorUnitTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user("asesor_notif", password="x")
        self.channel = WhatsAppChannel.objects.create(
            nombre="Canal test", phone_number_id="test-notif-conductor", activo=True,
        )
        self.vehiculo = Vehiculo.objects.create(
            placa="XYZ-999", marca="Nissan", modelo="NP300", capacidad_toneladas=1, activo=True,
        )
        self.conductor = Conductor.objects.create(
            nombre="Luis Ramirez", dni="87654321", telefono="+51900333444", activo=True,
        )
        self.servicio = Servicio.objects.create(
            codigo="SVC-9001", estado="pendiente",
            distrito_origen="Miraflores", distrito_destino="Surco",
            direccion_origen="Av. Larco 123", cliente=Cliente.objects.create(
                nombre="Cliente Demo", telefono="+51900111222",
            ),
        )
        self.programacion = ProgramacionServicio.objects.create(
            servicio=self.servicio, fecha=datetime.date.today(),
            vehiculo=self.vehiculo, conductor=self.conductor,
            hora_inicio=datetime.time(9, 0), monto=250,
            estado_operativo=ProgramacionServicio.ESTADO_PROGRAMADO,
        )

    def test_sin_conversacion_previa_no_envia_y_arma_mensaje(self):
        resultado = notificar_conductor_asignacion(self.programacion, self.actor)
        self.assertFalse(resultado["enviado"])
        self.assertIn("SVC-9001", resultado["mensaje"])
        self.assertIn("Miraflores", resultado["mensaje"])
        self.assertIsNotNone(resultado["motivo"])

    @patch("apps.whatsapp_bot_v4.services.ycloud_webhook_service.send_via_ycloud")
    def test_dentro_de_ventana_24h_envia(self, send_mock):
        send_mock.return_value = {"success": True, "wamid": "wamid.test123", "raw": {}}
        conv = crear_conversacion_manual(self.conductor.telefono, self.actor, nombre=self.conductor.nombre)
        conv.ultimo_mensaje_cliente = timezone.now() - datetime.timedelta(hours=2)
        conv.save(update_fields=["ultimo_mensaje_cliente"])

        resultado = notificar_conductor_asignacion(self.programacion, self.actor)
        self.assertTrue(resultado["enviado"], resultado["motivo"])
        self.assertIsNone(resultado["motivo"])
        self.assertTrue(conv.mensajes.filter(contenido__icontains="SVC-9001").exists())
        send_mock.assert_called_once()

    def test_fuera_de_ventana_24h_no_envia(self):
        conv = crear_conversacion_manual(self.conductor.telefono, self.actor, nombre=self.conductor.nombre)
        conv.ultimo_mensaje_cliente = timezone.now() - datetime.timedelta(hours=30)
        conv.save(update_fields=["ultimo_mensaje_cliente"])

        resultado = notificar_conductor_asignacion(self.programacion, self.actor)
        self.assertFalse(resultado["enviado"])
        self.assertIn("24h", resultado["motivo"])

    def test_conductor_sin_telefono_no_envia(self):
        self.conductor.telefono = ""
        self.conductor.save(update_fields=["telefono"])
        resultado = notificar_conductor_asignacion(self.programacion, self.actor)
        self.assertFalse(resultado["enviado"])
        self.assertIn("teléfono", resultado["motivo"])


class AsignarServicioPizarraViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        for group_name in ["Administrador", "Supervisor", "Asesor de Ventas"]:
            Group.objects.get_or_create(name=group_name)
        self.asesor = User.objects.create_user("asesor_pizarra", password="x")
        self.asesor.groups.add(Group.objects.get(name="Asesor de Ventas"))
        self.client.force_login(self.asesor)

        WhatsAppChannel.objects.create(
            nombre="Canal test", phone_number_id="test-asignar-pizarra", activo=True,
        )
        self.vehiculo = Vehiculo.objects.create(
            placa="AAA-111", marca="Kia", modelo="K2500", capacidad_toneladas=2, activo=True,
        )
        self.conductor = Conductor.objects.create(
            nombre="Jorge Diaz", dni="11223344", telefono="+51900555666", activo=True,
        )
        hoy = datetime.date.today()
        self.equipo = EquipoDia.objects.create(
            fecha=hoy, vehiculo=self.vehiculo, conductor=self.conductor, activo=True,
        )
        self.servicio = Servicio.objects.create(
            codigo="SVC-9100", estado="programado",
            fecha_servicio=hoy, horario_servicio="14:00",
        )

    def test_asignar_sin_conversacion_previa_devuelve_alerta_para_whatsapp_web(self):
        r = self.client.post(
            "/dashboard/campo/pizarra/programacion/asignar/",
            data=json.dumps({"servicio_id": self.servicio.id, "equipo_id": self.equipo.id}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data["status"], "ok")
        self.assertFalse(data["whatsapp_enviado"])
        self.assertIsNotNone(data["whatsapp_alerta"])
        self.assertIn("SVC-9100", data["whatsapp_mensaje"])
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.estado, "asignado")
