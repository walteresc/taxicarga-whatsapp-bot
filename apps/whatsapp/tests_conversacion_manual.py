"""Iniciar una conversación desde un número escrito a mano (asesor), sin que
haya llegado nada por webhook. apps.whatsapp.domain.crear_conversacion_manual
+ la vista apps.dashboard.views_whatsapp.api_crear_conversacion_manual."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.domain import TransicionConversacionInvalida, crear_conversacion_manual
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel

User = get_user_model()


class CrearConversacionManualTests(TestCase):
    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            nombre="Canal test", phone_number_id="test-manual", activo=True,
        )
        self.actor = User.objects.create_user("asesor_test", password="x")

    def test_crea_cliente_lead_y_conversacion(self):
        conv = crear_conversacion_manual("+51900111222", self.actor)
        self.assertEqual(conv.cliente.telefono, "+51900111222")
        self.assertIsNotNone(conv.lead_id)
        self.assertEqual(conv.channel_id, self.channel.id)
        self.assertEqual(Cliente.objects.filter(telefono="+51900111222").count(), 1)

    def test_mismo_numero_en_formatos_distintos_reusa_conversacion(self):
        conv1 = crear_conversacion_manual("+51900111222", self.actor)
        conv2 = crear_conversacion_manual("51 900 111 222", self.actor)
        self.assertEqual(conv1.id, conv2.id)
        self.assertEqual(conv1.cliente_id, conv2.cliente_id)
        self.assertEqual(Cliente.objects.filter(telefono="+51900111222").count(), 1)

    def test_numero_vacio_rechaza(self):
        with self.assertRaises(TransicionConversacionInvalida):
            crear_conversacion_manual("", self.actor)

    def test_sin_canal_activo_rechaza(self):
        self.channel.activo = False
        self.channel.save(update_fields=["activo"])
        with self.assertRaises(TransicionConversacionInvalida):
            crear_conversacion_manual("+51900111222", self.actor)

    def test_conversacion_nueva_no_tiene_mensajes(self):
        conv = crear_conversacion_manual("+51900111222", self.actor)
        self.assertEqual(conv.mensajes.count(), 0)

    def test_con_nombre_lo_guarda_como_manual(self):
        conv = crear_conversacion_manual("+51900111222", self.actor, nombre="Yancarlos")
        self.assertEqual(conv.cliente.nombre, "Yancarlos")
        self.assertEqual(conv.cliente.name_source, Cliente.SOURCE_MANUAL)

    def test_sin_nombre_usa_el_telefono_como_fallback(self):
        conv = crear_conversacion_manual("+51900111222", self.actor)
        self.assertEqual(conv.cliente.nombre, "+51900111222")
        self.assertEqual(conv.cliente.name_source, Cliente.SOURCE_FALLBACK)

    def test_nombre_no_pisa_uno_manual_ya_guardado(self):
        crear_conversacion_manual("+51900111222", self.actor, nombre="Yancarlos")
        conv = crear_conversacion_manual("+51900111222", self.actor, nombre="Otro Nombre")
        self.assertEqual(conv.cliente.nombre, "Yancarlos")


class CrearConversacionManualViewTests(TestCase):
    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            nombre="Canal test", phone_number_id="test-manual-view", activo=True,
        )
        self.user = User.objects.create_user("asesor_view", password="x")
        g, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        self.user.groups.add(g)
        self.client.force_login(self.user)

    def test_crea_conversacion_via_api(self):
        r = self.client.post(
            "/dashboard/whatsapp/conversaciones/nueva/",
            data='{"telefono": "+51900222333"}',
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data["status"], "ok")
        conv = ConversacionWhatsApp.objects.get(pk=data["conversation_id"])
        self.assertEqual(conv.cliente.telefono, "+51900222333")

    def test_numero_vacio_da_400(self):
        r = self.client.post(
            "/dashboard/whatsapp/conversaciones/nueva/",
            data='{"telefono": ""}',
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_requiere_login(self):
        self.client.logout()
        r = self.client.post(
            "/dashboard/whatsapp/conversaciones/nueva/",
            data='{"telefono": "+51900222333"}',
            content_type="application/json",
        )
        self.assertIn(r.status_code, (302, 401, 403))
