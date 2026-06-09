from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from unittest.mock import patch

from apps.clientes.models import Cliente, Conversacion
from apps.leads.models import Lead


class DashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="vendedor", password="pass123")
        self.cliente = Cliente.objects.create(nombre="Carlos Vega", telefono="51970000001")
        self.lead = Lead.objects.create(
            cliente=self.cliente,
            tipo_servicio="mudanza",
            distrito_origen="Miraflores",
            distrito_destino="Surco",
            estado=Lead.COTIZADO,
        )
        Conversacion.objects.create(
            cliente=self.cliente,
            mensaje_entrada="Quiero una mudanza",
            mensaje_salida="Claro, le ayudo.",
        )

    def test_dashboard_requiere_login(self):
        response = self.client.get(reverse("dashboard-home"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard/login/", response["Location"])

    def test_dashboard_login_renderiza_vuetify(self):
        response = self.client.get(reverse("dashboard-login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acceso comercial")
        self.assertContains(response, "vuetify.min.js")
        self.assertContains(response, "TaxiCarga")

    def test_dashboard_login_autentica_y_redirige(self):
        response = self.client.post(
            reverse("dashboard-login"),
            {"username": "vendedor", "password": "pass123", "next": "/dashboard/"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/dashboard/")

    def test_dashboard_muestra_lead_y_conversacion(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard-lead-detail", args=[self.lead.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Carlos Vega")
        self.assertEqual(response.context["dashboard_data"]["selectedLead"]["ruta"], "Miraflores -> Surco")
        self.assertEqual(response.context["dashboard_data"]["conversations"][0]["entrada"], "Quiero una mudanza")
        self.assertEqual(response.context["dashboard_data"]["messages"][0]["author"], "Cliente")
        self.assertEqual(response.context["dashboard_data"]["messages"][0]["text"], "Quiero una mudanza")
        self.assertEqual(response.context["dashboard_data"]["messages"][1]["author"], "TaxiCarga")
        self.assertEqual(response.context["dashboard_data"]["messages"][1]["text"], "Claro, le ayudo.")
        self.assertEqual(response.context["dashboard_data"]["selectedLead"]["completion"]["completed"], 2)
        self.assertEqual(response.context["dashboard_data"]["selectedLead"]["completion"]["total"], 7)
        self.assertEqual(response.context["dashboard_data"]["selectedLead"]["completion"]["percent"], 29)
        self.assertEqual(
            response.context["dashboard_data"]["selectedLead"]["completion"]["missing"][0]["key"],
            "objetos",
        )
        self.assertEqual(response.context["dashboard_data"]["createLeadUrl"], "/dashboard/leads/nuevo/")
        self.assertEqual(response.context["dashboard_data"]["exportLeadsUrl"], "/dashboard/exportar/leads.csv")
        self.assertContains(response, "v-app")
        self.assertContains(response, "chat-timeline")
        self.assertContains(response, "Datos para cotizar")
        self.assertContains(response, "Checklist comercial")
        self.assertContains(response, "Falta pedir")
        self.assertContains(response, "Datos comerciales")
        self.assertContains(response, "Guardar datos comerciales")
        self.assertContains(response, "Recalcular precio recomendado")
        self.assertContains(response, "Cierre comercial")
        self.assertContains(response, "Cerrar venta")
        self.assertContains(response, "Marcar perdido")
        self.assertContains(response, "Ingresos")
        self.assertContains(response, "Ticket promedio")
        self.assertContains(response, "Conversion")
        self.assertContains(response, "Nuevo lead")
        self.assertContains(response, "Buscar lead")
        self.assertContains(response, "Exportar")
        self.assertContains(response, "Proximo seguimiento")
        self.assertContains(response, "Respuestas rapidas")
        self.assertContains(response, "Pedir fotos")
        self.assertEqual(response.context["dashboard_data"]["quickReplies"][0]["key"], "confirmar_datos")
        self.assertIn("seguimientos_hoy", response.context["dashboard_data"]["stats"])

    def test_dashboard_calcula_metricas_comerciales(self):
        self.client.force_login(self.user)
        cliente_ganado = Cliente.objects.create(nombre="Venta Ganada", telefono="51911110000")
        cliente_perdido = Cliente.objects.create(nombre="Venta Perdida", telefono="51911110001")
        Lead.objects.create(
            cliente=cliente_ganado,
            estado=Lead.CERRADO,
            precio_final="600.00",
            fecha_cierre=timezone.now(),
        )
        Lead.objects.create(
            cliente=cliente_perdido,
            estado=Lead.PERDIDO,
            motivo_perdida="Sin presupuesto",
            fecha_cierre=timezone.now(),
        )

        response = self.client.get(reverse("dashboard-home"))
        stats = response.context["dashboard_data"]["stats"]

        self.assertEqual(stats["cerrados"], 1)
        self.assertEqual(stats["perdidos"], 1)
        self.assertEqual(stats["ingresos_cerrados"], "S/ 600")
        self.assertEqual(stats["ticket_promedio"], "S/ 600")
        self.assertEqual(stats["conversion_rate"], 50)

    def test_exportar_leads_requiere_login(self):
        response = self.client.get(reverse("dashboard-leads-export"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard/login/", response["Location"])

    def test_exportar_leads_csv(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard-leads-export"), {"estado": "cotizados"})
        content = response.content.decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("taxicarga_leads_cotizados", response["Content-Disposition"])
        self.assertIn("cliente,telefono,tipo_servicio", content)
        self.assertIn("Carlos Vega,51970000001,mudanza", content)
        self.assertIn("precio_final,fecha_cierre,motivo_perdida", content)

    def test_exportar_leads_filtra_por_estado(self):
        self.client.force_login(self.user)
        cliente = Cliente.objects.create(nombre="Lead Asignado", telefono="51922220000")
        Lead.objects.create(cliente=cliente, estado=Lead.ASIGNADO, tipo_servicio="carga")

        response = self.client.get(reverse("dashboard-leads-export"), {"estado": "asignados"})
        content = response.content.decode("utf-8-sig")

        self.assertIn("Lead Asignado", content)
        self.assertNotIn("Carlos Vega", content)

    def test_exportar_leads_incluye_datos_de_cierre(self):
        self.client.force_login(self.user)
        ganado = Cliente.objects.create(nombre="Cliente Cerrado", telefono="51933330000")
        perdido = Cliente.objects.create(nombre="Cliente Perdido", telefono="51933330001")
        Lead.objects.create(
            cliente=ganado,
            estado=Lead.CERRADO,
            tipo_servicio="mudanza",
            precio_final="700.00",
            fecha_cierre=timezone.now(),
        )
        Lead.objects.create(
            cliente=perdido,
            estado=Lead.PERDIDO,
            tipo_servicio="carga",
            motivo_perdida="Precio alto",
            fecha_cierre=timezone.now(),
        )

        response = self.client.get(reverse("dashboard-leads-export"), {"estado": "cerrados"})
        content = response.content.decode("utf-8-sig")

        self.assertIn("Cliente Cerrado", content)
        self.assertIn("700.00", content)
        self.assertIn("Cliente Perdido", content)
        self.assertIn("Precio alto", content)

    def test_accion_asignarme_desde_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("dashboard-lead-action", args=[self.lead.id]),
            {"action": "assign_me"},
        )

        self.lead.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.lead.vendedor_asignado, self.user)
        self.assertEqual(self.lead.estado, Lead.ASIGNADO)

    def test_crear_lead_manual_desde_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("dashboard-lead-create"),
            {
                "nombre": "Maria Solis",
                "telefono": "51988887777",
                "tipo_servicio": "mudanza",
                "distrito_origen": "Lince",
                "distrito_destino": "Surco",
                "fecha_servicio": "2026-06-20",
                "horario_servicio": "9am",
                "lista_objetos": "cama, cajas y mesa",
                "prioridad": Lead.PRIORIDAD_ALTA,
                "nota_interna": "Llamar por la tarde",
            },
        )

        cliente = Cliente.objects.get(telefono="51988887777")
        lead = cliente.leads.first()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(cliente.nombre, "Maria Solis")
        self.assertEqual(lead.estado, Lead.ASIGNADO)
        self.assertTrue(lead.atencion_humana)
        self.assertEqual(lead.vendedor_asignado, self.user)
        self.assertEqual(lead.distrito_origen, "Lince")
        self.assertEqual(str(lead.fecha_servicio), "2026-06-20")

    def test_accion_guardar_nota_desde_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("dashboard-lead-action", args=[self.lead.id]),
            {"action": "save_note", "nota": "Llamar a las 5pm"},
        )

        self.lead.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertIn("Llamar a las 5pm", self.lead.nota_interna)

    def test_actualizar_datos_comerciales_desde_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("dashboard-lead-action", args=[self.lead.id]),
            {
                "action": "update_details",
                "tipo_servicio": "mudanza completa",
                "distrito_origen": "San Isidro",
                "distrito_destino": "La Molina",
                "fecha_servicio": "2026-06-21",
                "horario_servicio": "10am",
                "piso_origen": "3",
                "piso_destino": "1",
                "ascensor_origen": "si",
                "ascensor_destino": "no",
                "lista_objetos": "sofa, cama y 12 cajas",
            },
        )

        self.lead.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.lead.tipo_servicio, "mudanza completa")
        self.assertEqual(self.lead.distrito_origen, "San Isidro")
        self.assertEqual(str(self.lead.fecha_servicio), "2026-06-21")
        self.assertEqual(self.lead.piso_origen, 3)
        self.assertTrue(self.lead.ascensor_origen)
        self.assertFalse(self.lead.ascensor_destino)
        self.assertIn("sofa", self.lead.lista_objetos)
        self.assertIsNotNone(self.lead.fecha_ultimo_seguimiento)

    def test_recalcular_cotizacion_desde_dashboard(self):
        self.client.force_login(self.user)
        self.lead.lista_objetos = "sofa, cama y 12 cajas"
        self.lead.fecha_servicio = timezone.localdate()
        self.lead.horario_servicio = "10am"
        self.lead.piso_origen = 3
        self.lead.piso_destino = 1
        self.lead.ascensor_origen = True
        self.lead.ascensor_destino = False
        self.lead.save()

        response = self.client.post(
            reverse("dashboard-lead-action", args=[self.lead.id]),
            {"action": "recalculate_quote"},
        )

        self.lead.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self.lead.precio_estimado_min)
        self.assertIsNotNone(self.lead.precio_estimado_max)
        self.assertIsNotNone(self.lead.precio_recomendado)
        self.assertEqual(self.lead.cotizaciones.count(), 1)
        self.assertIsNotNone(self.lead.fecha_ultimo_seguimiento)

    def test_cerrar_venta_desde_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("dashboard-lead-action", args=[self.lead.id]),
            {"action": "close_won", "precio_final": "520.00"},
        )

        self.lead.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.lead.estado, Lead.CERRADO)
        self.assertEqual(str(self.lead.precio_final), "520.00")
        self.assertTrue(self.lead.atencion_humana)
        self.assertIsNotNone(self.lead.fecha_cierre)
        self.assertIsNotNone(self.lead.fecha_ultimo_seguimiento)

    def test_marcar_perdido_desde_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("dashboard-lead-action", args=[self.lead.id]),
            {"action": "close_lost", "motivo_perdida": "Cliente eligio otro proveedor"},
        )

        self.lead.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.lead.estado, Lead.PERDIDO)
        self.assertEqual(self.lead.motivo_perdida, "Cliente eligio otro proveedor")
        self.assertTrue(self.lead.atencion_humana)
        self.assertIsNotNone(self.lead.fecha_cierre)
        self.assertIsNotNone(self.lead.fecha_ultimo_seguimiento)

    def test_programar_proximo_seguimiento(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("dashboard-lead-action", args=[self.lead.id]),
            {
                "action": "schedule_follow_up",
                "fecha_proximo_seguimiento": "2026-06-20T15:30",
            },
        )

        self.lead.refresh_from_db()
        scheduled = timezone.localtime(self.lead.fecha_proximo_seguimiento)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(scheduled.strftime("%Y-%m-%dT%H:%M"), "2026-06-20T15:30")
        self.assertIsNotNone(self.lead.fecha_ultimo_seguimiento)

    def test_accion_tomar_y_liberar_conversacion(self):
        self.client.force_login(self.user)

        self.client.post(
            reverse("dashboard-lead-action", args=[self.lead.id]),
            {"action": "take_over"},
        )
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.atencion_humana)
        self.assertEqual(self.lead.vendedor_asignado, self.user)
        self.assertEqual(self.lead.estado, Lead.ASIGNADO)

        self.client.post(
            reverse("dashboard-lead-action", args=[self.lead.id]),
            {"action": "release"},
        )
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.atencion_humana)

    @patch("apps.dashboard.views.send_whatsapp_message")
    def test_respuesta_manual_se_guarda_en_conversacion(self, send_mock):
        send_mock.return_value = {"sent": False, "reason": "test"}
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("dashboard-lead-action", args=[self.lead.id]),
            {"action": "manual_reply", "respuesta": "Claro, lo reviso y le confirmo."},
        )

        self.lead.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.lead.atencion_humana)
        self.assertTrue(
            Conversacion.objects.filter(
                cliente=self.cliente,
                mensaje_salida="Claro, lo reviso y le confirmo.",
            ).exists()
        )
        send_mock.assert_called_once_with(self.cliente.telefono, "Claro, lo reviso y le confirmo.")

    @patch("apps.dashboard.views.send_whatsapp_message")
    def test_enviar_cotizacion_actualiza_precio_y_conversacion(self, send_mock):
        send_mock.return_value = {"sent": False, "reason": "test"}
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("dashboard-lead-action", args=[self.lead.id]),
            {
                "action": "send_quote",
                "precio_cotizado": "480.00",
                "mensaje_cotizacion": "Le dejamos la mudanza en S/ 480.",
            },
        )

        self.lead.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(str(self.lead.precio_cotizado), "480.00")
        self.assertEqual(self.lead.estado, Lead.COTIZADO)
        self.assertTrue(self.lead.atencion_humana)
        self.assertTrue(
            Conversacion.objects.filter(
                cliente=self.cliente,
                mensaje_salida="Le dejamos la mudanza en S/ 480.",
            ).exists()
        )
        send_mock.assert_called_once_with(self.cliente.telefono, "Le dejamos la mudanza en S/ 480.")
