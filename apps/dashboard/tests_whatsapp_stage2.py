from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.cotizador.models import CotizacionComercial, RevisionCotizacion, SolicitudCotizacion
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp


class WhatsAppBaseRoutesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.admin = user_model.objects.create_user(username="admin_stage2", password="x")
        cls.asesor = user_model.objects.create_user(username="asesor_stage2", password="x")
        cls.conductor = user_model.objects.create_user(username="conductor_stage2", password="x")
        for name, user in [
            ("Administrador", cls.admin),
            ("Asesor de Ventas", cls.asesor),
            ("Conductor", cls.conductor),
        ]:
            group, _ = Group.objects.get_or_create(name=name)
            user.groups.add(group)
        cls.cliente = Cliente.objects.create(nombre="Cliente Ruta Stage2", telefono="51900000022")
        cls.lead = Lead.objects.create(
            cliente=cls.cliente,
            distrito_origen="Surco",
            distrito_destino="Miraflores",
        )
        cls.conversacion = ConversacionWhatsApp.objects.create(cliente=cls.cliente, lead=cls.lead)
        cls.solicitud = SolicitudCotizacion.objects.create(
            lead=cls.lead,
            conversacion=cls.conversacion,
            motivo="Objeto especial",
        )
        cls.cotizacion = CotizacionComercial.objects.create(
            codigo="COT-STAGE2-001",
            lead=cls.lead,
            solicitud=cls.solicitud,
            origen="asesor",
            asesor=cls.asesor,
        )
        RevisionCotizacion.objects.create(
            cotizacion=cls.cotizacion,
            numero=1,
            creada_por=cls.asesor,
            precio_final=580,
        )

    def test_rutas_requieren_login(self):
        response = self.client.get(reverse("dashboard-whatsapp-conversaciones"))
        self.assertEqual(response.status_code, 302)

    def test_asesor_accede_a_tres_rutas_operativas(self):
        self.client.force_login(self.asesor)
        for name in [
            "dashboard-whatsapp-conversaciones",
            "dashboard-whatsapp-por-cotizar",
            "dashboard-whatsapp-cotizaciones",
        ]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_asesor_no_configura_bot(self):
        self.client.force_login(self.asesor)
        self.assertEqual(self.client.get(reverse("dashboard-whatsapp-configuracion")).status_code, 403)

    def test_administrador_accede_configuracion(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard-whatsapp-configuracion"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configuración del Bot")

    def test_conductor_no_accede_modulo(self):
        self.client.force_login(self.conductor)
        self.assertEqual(self.client.get(reverse("dashboard-whatsapp-conversaciones")).status_code, 403)

    def test_vistas_muestran_datos_reales(self):
        self.client.force_login(self.asesor)
        conversaciones = self.client.get(reverse("dashboard-whatsapp-conversaciones"))
        pendientes = self.client.get(reverse("dashboard-whatsapp-por-cotizar"))
        cotizaciones = self.client.get(reverse("dashboard-whatsapp-cotizaciones"))
        self.assertContains(conversaciones, "Cliente Ruta Stage2")
        self.assertContains(pendientes, "Objeto especial")
        self.assertContains(cotizaciones, "COT-STAGE2-001")
        self.assertContains(cotizaciones, "S/ 580.00")

    def test_sidebar_muestra_grupo_whatsapp(self):
        self.client.force_login(self.asesor)
        response = self.client.get(reverse("dashboard-whatsapp-conversaciones"))
        self.assertContains(response, "WHATSAPP")
        self.assertContains(response, "Conversaciones")
        self.assertContains(response, "Por cotizar")
        self.assertContains(response, "Cotizaciones")
        self.assertNotContains(response, "Configuración del bot")
