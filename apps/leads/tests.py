from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from apps.leads.admin import LeadAdmin
from apps.clientes.models import Cliente, Conversacion
from apps.leads.models import Lead


class LeadApiTests(TestCase):
    def test_endpoint_pendientes_devuelve_resumen(self):
        cliente = Cliente.objects.create(nombre="Luis Ramos", telefono="51966666666")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Lince",
            distrito_destino="Surco",
            estado=Lead.DATOS_INCOMPLETOS,
            prioridad=Lead.PRIORIDAD_ALTA,
        )

        response = self.client.get(reverse("lead-pendientes"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["cliente_nombre"], "Luis Ramos")
        self.assertEqual(response.json()[0]["ruta"], "Lince -> Surco")
        self.assertEqual(response.json()[0]["prioridad"], Lead.PRIORIDAD_ALTA)

    def test_endpoint_cotizados_devuelve_precio(self):
        cliente = Cliente.objects.create(nombre="Rosa Diaz", telefono="51911112222")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="carga",
            distrito_origen="Barranco",
            distrito_destino="San Isidro",
            estado=Lead.COTIZADO,
            precio_recomendado=Decimal("280.00"),
        )

        response = self.client.get(reverse("lead-cotizados"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["precio_recomendado"], "280.00")

    def test_registrar_nota_actualiza_lead(self):
        user = get_user_model().objects.create_user(username="vendedor", password="pass123")
        self.client.force_login(user)
        cliente = Cliente.objects.create(nombre="Mario Rios", telefono="51933334444")
        lead = Lead.objects.create(cliente=cliente, estado=Lead.COTIZADO)

        response = self.client.post(
            reverse("lead-registrar-nota", args=[lead.id]),
            {"nota": "Cliente pidio llamada a las 5pm"},
            content_type="application/json",
        )

        lead.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Cliente pidio llamada", lead.nota_interna)
        self.assertIsNotNone(lead.fecha_ultimo_seguimiento)

    def test_cambiar_estado_a_cerrado_registra_fecha_cierre(self):
        user = get_user_model().objects.create_user(username="vendedor2", password="pass123")
        self.client.force_login(user)
        cliente = Cliente.objects.create(nombre="Elena Ruiz", telefono="51922223333")
        lead = Lead.objects.create(cliente=cliente, estado=Lead.COTIZADO)

        response = self.client.post(
            reverse("lead-cambiar-estado", args=[lead.id]),
            {"estado": Lead.CERRADO},
            content_type="application/json",
        )

        lead.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(lead.estado, Lead.CERRADO)
        self.assertIsNotNone(lead.fecha_cierre)

    @patch("apps.leads.views.send_whatsapp_message")
    def test_registrar_cotizacion_actualiza_precio_y_envia_mensaje(self, send_mock):
        send_mock.return_value = {"sent": False, "reason": "test"}
        user = get_user_model().objects.create_user(username="vendedor3", password="pass123")
        self.client.force_login(user)
        cliente = Cliente.objects.create(nombre="Nora Paz", telefono="51910002000")
        lead = Lead.objects.create(
            cliente=cliente,
            estado=Lead.ASIGNADO,
            distrito_origen="Miraflores",
            distrito_destino="Surco",
        )

        response = self.client.post(
            reverse("lead-registrar-cotizacion", args=[lead.id]),
            {"precio_cotizado": "510.00", "mensaje": "La cotizacion queda en S/ 510."},
            content_type="application/json",
        )

        lead.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(lead.precio_cotizado), "510.00")
        self.assertEqual(lead.estado, Lead.COTIZADO)
        self.assertTrue(lead.atencion_humana)
        self.assertTrue(Conversacion.objects.filter(cliente=cliente, mensaje_salida__contains="510").exists())
        send_mock.assert_called_once_with(cliente.telefono, "La cotizacion queda en S/ 510.")


class LeadAdminTests(TestCase):
    def test_accion_asignarme_asigna_usuario_y_estado(self):
        user = get_user_model().objects.create_user(username="adminvendedor", password="pass123")
        cliente = Cliente.objects.create(nombre="Tania Soto", telefono="51912121212")
        lead = Lead.objects.create(cliente=cliente, estado=Lead.COTIZADO)
        request = RequestFactory().post("/")
        request.user = user
        admin = LeadAdmin(Lead, AdminSite())

        with patch.object(admin, "message_user"):
            admin.asignarme(request, Lead.objects.filter(id=lead.id))

        lead.refresh_from_db()
        self.assertEqual(lead.vendedor_asignado, user)
        self.assertEqual(lead.estado, Lead.ASIGNADO)
