from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.cotizador.models import CotizacionComercial, EnvioCotizacion, RevisionCotizacion, SolicitudCotizacion
from apps.leads.models import Lead


class WhatsAppQuoteDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        cls.advisor = users.objects.create_user("detail_advisor", password="x")
        cls.advisor.groups.add(group)
        cls.customer = Cliente.objects.create(nombre="Cliente Detalle", telefono="51944444777")
        cls.lead = Lead.objects.create(
            cliente=cls.customer,
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            lista_objetos="Sofá, mesa y cajas",
        )
        cls.request_record = SolicitudCotizacion.objects.create(lead=cls.lead, asignada_a=cls.advisor)
        cls.quote = CotizacionComercial.objects.create(
            codigo="COT-DETAIL-001",
            lead=cls.lead,
            solicitud=cls.request_record,
            origen="asesor",
            asesor=cls.advisor,
        )
        cls.v1 = RevisionCotizacion.objects.create(
            cotizacion=cls.quote, numero=1, creada_por=cls.advisor, precio_final=580,
            condiciones="Incluye unidad y personal", mensaje_whatsapp="Mensaje versión uno",
        )
        cls.v2 = RevisionCotizacion.objects.create(
            cotizacion=cls.quote, numero=2, creada_por=cls.advisor, precio_final=620,
            condiciones="Incluye embalaje", mensaje_whatsapp="Mensaje versión dos",
        )
        EnvioCotizacion.objects.create(revision=cls.v1, estado="error", error_detalle="Meta rechazó el envío")

    def setUp(self):
        self.client.force_login(self.advisor)

    @property
    def url(self):
        return reverse("dashboard-whatsapp-cotizacion-detalle", args=[self.quote.id])

    def test_renders_general_service_and_latest_price(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "COT-DETAIL-001")
        self.assertContains(response, "Cliente Detalle")
        self.assertContains(response, "Surco → Miraflores")
        self.assertContains(response, "S/ 620.00")

    def test_renders_all_revisions_and_messages(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Versión 1")
        self.assertContains(response, "Versión 2")
        self.assertContains(response, "Mensaje versión uno")
        self.assertContains(response, "Mensaje versión dos")

    def test_timeline_contains_creation_revisions_and_delivery_error(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Cotización creada")
        self.assertContains(response, "Revisión v2 creada")
        self.assertContains(response, "Intento de envío: Error")
        self.assertContains(response, "Meta rechazó el envío")

    def test_history_links_to_detail(self):
        response = self.client.get(reverse("dashboard-whatsapp-cotizaciones"))
        self.assertContains(response, self.url)

    def test_detail_action_redirects_back_to_detail(self):
        self.quote.estado = "enviada"
        self.quote.save()
        action = reverse("dashboard-whatsapp-cotizacion-accion", args=[self.quote.id])
        response = self.client.post(action, {"state": "en_negociacion", "next": "detail"})
        self.assertRedirects(response, self.url)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.estado, "en_negociacion")

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
