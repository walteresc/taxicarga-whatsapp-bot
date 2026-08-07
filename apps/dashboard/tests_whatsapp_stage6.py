from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.cotizador.commercial import cambiar_estado_cotizacion
from apps.cotizador.models import CotizacionComercial, RevisionCotizacion, SolicitudCotizacion
from apps.leads.models import Lead


class WhatsAppQuoteHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        cls.advisor = users.objects.create_user("history_advisor", password="x")
        cls.advisor.groups.add(group)
        cls.customer = Cliente.objects.create(nombre="Cliente Historial", telefono="51933333666")
        cls.lead = Lead.objects.create(cliente=cls.customer, distrito_origen="Surco", distrito_destino="Ate")
        cls.request_record = SolicitudCotizacion.objects.create(lead=cls.lead, asignada_a=cls.advisor)
        cls.quote = CotizacionComercial.objects.create(
            codigo="COT-HISTORY-001",
            lead=cls.lead,
            solicitud=cls.request_record,
            origen="asesor",
            asesor=cls.advisor,
        )
        cls.revision = RevisionCotizacion.objects.create(
            cotizacion=cls.quote,
            numero=1,
            creada_por=cls.advisor,
            precio_final=580,
        )

    def setUp(self):
        self.client.force_login(self.advisor)

    def test_renders_metrics_real_quote_and_latest_revision(self):
        response = self.client.get(reverse("dashboard-whatsapp-cotizaciones"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total este mes")
        self.assertContains(response, "COT-HISTORY-001")
        self.assertContains(response, "Cliente Historial")
        self.assertContains(response, "S/ 580.00")

    def test_search_state_origin_and_advisor_filters(self):
        url = reverse("dashboard-whatsapp-cotizaciones")
        response = self.client.get(url, {"q": "HISTORY", "state": "borrador", "origin": "asesor", "advisor": self.advisor.id})
        self.assertContains(response, "COT-HISTORY-001")
        response = self.client.get(url, {"q": "No existe"})
        self.assertNotContains(response, "COT-HISTORY-001")

    def test_cancel_draft_is_allowed(self):
        url = reverse("dashboard-whatsapp-cotizacion-accion", args=[self.quote.id])
        response = self.client.post(url, {"state": "cancelada"})
        self.assertRedirects(response, reverse("dashboard-whatsapp-cotizaciones"))
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.estado, "cancelada")

    def test_invalid_transition_is_rejected(self):
        url = reverse("dashboard-whatsapp-cotizacion-accion", args=[self.quote.id])
        self.client.post(url, {"state": "aceptada"})
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.estado, "borrador")

    def test_sent_quote_can_enter_negotiation_and_be_accepted(self):
        self.quote.estado = "enviada"
        self.quote.save()
        cambiar_estado_cotizacion(self.quote.id, "en_negociacion")
        cambiar_estado_cotizacion(self.quote.id, "aceptada")
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.estado, "aceptada")

    def test_latest_revision_is_displayed(self):
        RevisionCotizacion.objects.create(
            cotizacion=self.quote,
            numero=2,
            creada_por=self.advisor,
            precio_final=620,
        )
        response = self.client.get(reverse("dashboard-whatsapp-cotizaciones"))
        self.assertContains(response, "S/ 620.00")
        self.assertContains(response, "v2")
