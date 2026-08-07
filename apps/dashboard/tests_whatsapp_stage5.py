from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.cotizador.models import CotizacionComercial, RevisionCotizacion, SolicitudCotizacion
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp


class WhatsAppCreateQuoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        cls.advisor = users.objects.create_user("create_quote_advisor", password="x")
        cls.other = users.objects.create_user("create_quote_other", password="x")
        cls.advisor.groups.add(group)
        cls.other.groups.add(group)
        cls.customer = Cliente.objects.create(nombre="Cliente Cotización", telefono="51922222555")
        cls.lead = Lead.objects.create(
            cliente=cls.customer,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            lista_objetos="Sofá y 4 cajas",
        )
        cls.conversation = ConversacionWhatsApp.objects.create(
            cliente=cls.customer,
            lead=cls.lead,
            porcentaje_informacion=80,
            estado_cotizacion=ConversacionWhatsApp.COTIZACION_PENDIENTE,
        )
        cls.request_record = SolicitudCotizacion.objects.create(
            lead=cls.lead,
            conversacion=cls.conversation,
            motivo="Revisión de precio",
        )

    def setUp(self):
        self.client.force_login(self.advisor)

    @property
    def url(self):
        return reverse("dashboard-whatsapp-crear-cotizacion", args=[self.request_record.id])

    def _payload(self, **updates):
        data = {
            "price": "580",
            "cost": "400",
            "margin": "20",
            "validity": "7",
            "conditions": "Incluye unidad y personal.",
            "internal_note": "Pago por confirmar.",
            "message": "Hola, precio total S/ 580.",
        }
        data.update(updates)
        return data

    def test_renders_summary_suggestion_and_preview(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Crear cotización")
        self.assertContains(response, "Surco → Miraflores")
        self.assertContains(response, "Precio sugerido")
        self.assertContains(response, "Vista previa WhatsApp")

    def test_get_does_not_assign_request(self):
        self.client.get(self.url)
        self.request_record.refresh_from_db()
        self.assertIsNone(self.request_record.asignada_a)

    def test_saves_versioned_draft_and_snapshot(self):
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, 302)
        quote = CotizacionComercial.objects.get(solicitud=self.request_record)
        revision = quote.revisiones.get()
        self.assertEqual(revision.precio_final, 580)
        self.assertEqual(revision.snapshot_servicio["origen"], "Surco")
        self.assertEqual(revision.mensaje_whatsapp, "Hola, precio total S/ 580.")

    def test_second_save_creates_new_revision_not_new_quote(self):
        self.client.post(self.url, self._payload())
        self.client.post(self.url, self._payload(price="610"))
        self.assertEqual(CotizacionComercial.objects.filter(solicitud=self.request_record).count(), 1)
        self.assertEqual(RevisionCotizacion.objects.filter(cotizacion__solicitud=self.request_record).count(), 2)
        self.assertEqual(RevisionCotizacion.objects.filter(cotizacion__solicitud=self.request_record).order_by("-numero").first().precio_final, 610)

    def test_rejects_price_below_margin(self):
        response = self.client.post(self.url, self._payload(price="450", cost="400", margin="20"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no cumple el margen minimo")
        self.assertFalse(CotizacionComercial.objects.filter(solicitud=self.request_record).exists())

    def test_other_advisor_cannot_open_assigned_request(self):
        self.request_record.asignada_a = self.other
        self.request_record.estado = SolicitudCotizacion.EN_PROCESO
        self.request_record.save()
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("dashboard-whatsapp-por-cotizar"))

    def test_no_whatsapp_message_is_sent_when_saving(self):
        self.client.post(self.url, self._payload())
        revision = RevisionCotizacion.objects.get(cotizacion__solicitud=self.request_record)
        self.assertFalse(revision.enviada)
