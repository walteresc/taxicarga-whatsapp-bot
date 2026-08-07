from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.clientes.models import Cliente
from apps.cotizador.models import SolicitudCotizacion
from apps.leads.models import Lead

from .domain import (
    ConversacionOcupada,
    devolver_al_bot,
    enviar_a_cotizar,
    obtener_o_crear_conversacion,
    tomar_conversacion,
)
from .models import AuditoriaWhatsApp, ConversacionWhatsApp, MensajeWhatsApp


class ConversationStateTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(telefono="51900000001", nombre="Cliente etapa 1")
        self.lead = Lead.objects.create(cliente=self.cliente)
        user_model = get_user_model()
        self.asesor = user_model.objects.create_user(username="asesor_stage1", password="x")
        self.otro = user_model.objects.create_user(username="otro_stage1", password="x")
        self.conversacion = obtener_o_crear_conversacion(self.lead)

    def test_una_conversacion_activa_por_lead(self):
        with self.assertRaises(IntegrityError):
            ConversacionWhatsApp.objects.create(cliente=self.cliente, lead=self.lead)

    def test_tomar_conversacion_pausa_bot_y_audita(self):
        tomar_conversacion(self.conversacion.id, self.asesor)
        self.conversacion.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertEqual(self.conversacion.estado_atencion, ConversacionWhatsApp.ATENCION_ASESOR)
        self.assertEqual(self.conversacion.responsable, self.asesor)
        self.assertTrue(self.conversacion.bot_pausado)
        self.assertTrue(self.lead.atencion_humana)
        self.assertTrue(self.lead.bot_pausado)
        self.assertTrue(AuditoriaWhatsApp.objects.filter(evento="conversacion_tomada").exists())

    def test_otro_asesor_no_puede_tomar_conversacion(self):
        tomar_conversacion(self.conversacion.id, self.asesor)
        with self.assertRaises(ConversacionOcupada):
            tomar_conversacion(self.conversacion.id, self.otro)

    def test_devolver_al_bot_conserva_precio_y_guarda_instruccion(self):
        self.lead.precio_cotizado = 580
        self.lead.save(update_fields=["precio_cotizado"])
        tomar_conversacion(self.conversacion.id, self.asesor)
        devolver_al_bot(self.conversacion.id, self.asesor, "seguimiento_cotizacion")
        self.conversacion.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertEqual(self.conversacion.estado_atencion, ConversacionWhatsApp.ATENCION_BOT)
        self.assertEqual(self.conversacion.instruccion_retorno_bot, "seguimiento_cotizacion")
        self.assertEqual(self.lead.precio_cotizado, 580)
        self.assertFalse(self.lead.atencion_humana)

    def test_enviar_a_cotizar_no_duplica_pendiente(self):
        primera = enviar_a_cotizar(self.conversacion.id, self.asesor, "Caso complejo")
        segunda = enviar_a_cotizar(self.conversacion.id, self.asesor, "Caso complejo")
        self.assertEqual(primera.id, segunda.id)
        self.assertEqual(SolicitudCotizacion.objects.count(), 1)

    def test_meta_message_id_no_se_duplica(self):
        MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            meta_message_id="wamid.stage1",
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
        )
        with self.assertRaises(IntegrityError):
            MensajeWhatsApp.objects.create(
                conversacion=self.conversacion,
                meta_message_id="wamid.stage1",
                direccion=MensajeWhatsApp.ENTRANTE,
                origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            )
