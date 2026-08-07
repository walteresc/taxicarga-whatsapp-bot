from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente, Conversacion
from apps.cotizador.models import SolicitudCotizacion
from apps.leads.models import Lead
from apps.whatsapp.models import AuditoriaWhatsApp, ConversacionWhatsApp, MensajeWhatsApp


class WhatsAppConversationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        user_model = get_user_model()
        cls.asesor = user_model.objects.create_user(username="asesor_stage3", password="x")
        cls.otro = user_model.objects.create_user(username="otro_stage3", password="x")
        cls.asesor.groups.add(group)
        cls.otro.groups.add(group)
        cls.cliente = Cliente.objects.create(nombre="Maria Conversacion", telefono="51900000033")
        cls.lead = Lead.objects.create(
            cliente=cls.cliente,
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            lista_objetos="Sofa y cajas",
        )
        cls.conversacion = ConversacionWhatsApp.objects.create(
            cliente=cls.cliente,
            lead=cls.lead,
            resumen="Mudanza residencial de prueba",
            datos_faltantes=["fecha"],
            porcentaje_informacion=70,
        )
        Conversacion.objects.create(
            cliente=cls.cliente,
            mensaje_entrada="Necesito una mudanza",
            mensaje_salida="Indiqueme origen y destino",
        )

    def setUp(self):
        self.client.force_login(self.asesor)

    def test_renderiza_tres_columnas_con_historial_legacy(self):
        response = self.client.get(reverse("dashboard-whatsapp-conversaciones"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Maria Conversacion")
        self.assertContains(response, "Necesito una mudanza")
        self.assertContains(response, "Ficha del servicio")
        self.assertContains(response, "Sofa y cajas")

    def test_busqueda_y_filtro_estado(self):
        response = self.client.get(reverse("dashboard-whatsapp-conversaciones"), {"q": "Maria", "state": "bot"})
        self.assertContains(response, "Maria Conversacion")
        response = self.client.get(reverse("dashboard-whatsapp-conversaciones"), {"q": "inexistente"})
        self.assertContains(response, "No hay conversaciones con estos filtros")

    def test_tomar_y_devolver_al_bot_audita(self):
        action_url = reverse("dashboard-whatsapp-conversacion-accion", args=[self.conversacion.id])
        self.client.post(action_url, {"action": "take"})
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.responsable, self.asesor)
        self.assertTrue(self.conversacion.bot_pausado)
        self.client.post(action_url, {"action": "return_bot", "instruction": "resolver_preguntas"})
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.estado_atencion, "bot")
        self.assertEqual(self.conversacion.instruccion_retorno_bot, "resolver_preguntas")
        self.assertEqual(AuditoriaWhatsApp.objects.filter(conversacion=self.conversacion).count(), 2)

    def test_otro_asesor_no_puede_reasignar(self):
        action_url = reverse("dashboard-whatsapp-conversacion-accion", args=[self.conversacion.id])
        self.client.post(action_url, {"action": "take"})
        self.client.force_login(self.otro)
        self.client.post(action_url, {"action": "take"})
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.responsable, self.asesor)

    def test_enviar_a_cotizar_no_duplica(self):
        action_url = reverse("dashboard-whatsapp-conversacion-accion", args=[self.conversacion.id])
        self.client.post(action_url, {"action": "quote"})
        self.client.post(action_url, {"action": "quote"})
        self.assertEqual(SolicitudCotizacion.objects.filter(lead=self.lead).count(), 1)

    @patch("apps.dashboard.views_whatsapp.send_whatsapp_message")
    def test_respuesta_toma_conversacion_y_normaliza_mensaje(self, send_mock):
        send_mock.return_value = {"messages": [{"id": "wamid.stage3"}]}
        action_url = reverse("dashboard-whatsapp-conversacion-accion", args=[self.conversacion.id])
        self.client.post(action_url, {"action": "reply", "message": "Le confirmo en unos minutos."})
        self.conversacion.refresh_from_db()
        mensaje = MensajeWhatsApp.objects.get(meta_message_id="wamid.stage3")
        self.assertEqual(mensaje.origen, MensajeWhatsApp.ORIGEN_ASESOR)
        self.assertEqual(mensaje.autor, self.asesor)
        self.assertEqual(self.conversacion.responsable, self.asesor)
        send_mock.assert_called_once_with(self.cliente.telefono, "Le confirmo en unos minutos.")

    def test_cerrar_pausa_bot_y_oculta_compositor(self):
        action_url = reverse("dashboard-whatsapp-conversacion-accion", args=[self.conversacion.id])
        self.client.post(action_url, {"action": "close"})
        self.conversacion.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertEqual(self.conversacion.estado_atencion, "cerrada")
        self.assertTrue(self.lead.bot_pausado)
        response = self.client.get(reverse("dashboard-whatsapp-conversaciones"), {"state": "closed"})
        self.assertNotContains(response, "Escribe un mensaje...")
