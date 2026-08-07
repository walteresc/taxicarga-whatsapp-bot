from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.cotizador.models import SolicitudCotizacion
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp


class WhatsAppQuoteQueueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        cls.advisor = users.objects.create_user("queue_advisor", password="x")
        cls.other = users.objects.create_user("queue_other", password="x")
        cls.advisor.groups.add(group)
        cls.other.groups.add(group)
        cls.client_record = Cliente.objects.create(nombre="Maria Queue", telefono="51911111444")
        cls.lead = Lead.objects.create(
            cliente=cls.client_record,
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            prioridad=Lead.PRIORIDAD_URGENTE,
        )
        cls.conversation = ConversacionWhatsApp.objects.create(
            cliente=cls.client_record,
            lead=cls.lead,
            porcentaje_informacion=75,
            estado_cotizacion=ConversacionWhatsApp.COTIZACION_PENDIENTE,
        )
        cls.quote_request = SolicitudCotizacion.objects.create(
            lead=cls.lead,
            conversacion=cls.conversation,
            motivo="Datos faltantes",
            prioridad=Lead.PRIORIDAD_URGENTE,
        )

    def setUp(self):
        self.client.force_login(self.advisor)

    def test_queue_renders_metrics_and_real_data(self):
        response = self.client.get(reverse("dashboard-whatsapp-por-cotizar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pendientes")
        self.assertContains(response, "Urgentes")
        self.assertContains(response, "Maria Queue")
        self.assertContains(response, "Surco → Miraflores")
        self.assertContains(response, "75%")

    def test_search_priority_and_unassigned_filters(self):
        url = reverse("dashboard-whatsapp-por-cotizar")
        response = self.client.get(url, {"q": "Maria", "priority": "urgente", "advisor": "unassigned"})
        self.assertContains(response, "Maria Queue")
        response = self.client.get(url, {"q": "No existe"})
        self.assertNotContains(response, "Maria Queue")

    def test_assign_is_atomic_and_syncs_lead_and_conversation(self):
        url = reverse("dashboard-whatsapp-solicitud-accion", args=[self.quote_request.id])
        response = self.client.post(url, {"action": "assign"})
        self.assertRedirects(response, reverse("dashboard-whatsapp-por-cotizar"))
        self.quote_request.refresh_from_db()
        self.lead.refresh_from_db()
        self.conversation.refresh_from_db()
        self.assertEqual(self.quote_request.estado, SolicitudCotizacion.EN_PROCESO)
        self.assertEqual(self.quote_request.asignada_a, self.advisor)
        self.assertEqual(self.lead.vendedor_asignado, self.advisor)
        self.assertEqual(self.conversation.responsable, self.advisor)

    def test_other_advisor_cannot_take_assigned_request(self):
        self.quote_request.asignada_a = self.other
        self.quote_request.estado = SolicitudCotizacion.EN_PROCESO
        self.quote_request.save()
        url = reverse("dashboard-whatsapp-solicitud-accion", args=[self.quote_request.id])
        self.client.post(url, {"action": "assign"})
        self.quote_request.refresh_from_db()
        self.assertEqual(self.quote_request.asignada_a, self.other)

    def test_quote_takes_request_and_redirects_to_create_quote(self):
        url = reverse("dashboard-whatsapp-solicitud-accion", args=[self.quote_request.id])
        response = self.client.post(url, {"action": "quote"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard-whatsapp-crear-cotizacion", args=[self.quote_request.id]))
        self.quote_request.refresh_from_db()
        self.assertEqual(self.quote_request.asignada_a, self.advisor)

    def test_completed_requests_are_hidden(self):
        self.quote_request.estado = SolicitudCotizacion.TERMINADA
        self.quote_request.save()
        response = self.client.get(reverse("dashboard-whatsapp-por-cotizar"))
        self.assertNotContains(response, "Maria Queue")
