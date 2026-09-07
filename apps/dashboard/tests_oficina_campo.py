"""Particiones 'Oficina' (manual) y 'Campo' (auto-detectada por teléfono
contra Conductor/Ayudante) en /whatsapp/conversaciones/api/active/."""
import json

from django.contrib.auth.models import Group, User
from django.test import TestCase

from apps.campo.models import Ayudante, Conductor
from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel


class OficinaCampoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("asesor_test", password="x")
        g, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        self.user.groups.add(g)
        self.client.force_login(self.user)

        self.channel = WhatsAppChannel.objects.create(
            nombre="Canal test", phone_number_id="test-oficina-campo", activo=True,
        )

        self.cliente_regular = Cliente.objects.create(nombre="Cliente normal", telefono="+51900000001")
        self.conv_regular = ConversacionWhatsApp.objects.create(cliente=self.cliente_regular, channel=self.channel)

        self.cliente_conductor = Cliente.objects.create(nombre="Chofer", telefono="+51900000002")
        self.conv_conductor = ConversacionWhatsApp.objects.create(cliente=self.cliente_conductor, channel=self.channel)
        Conductor.objects.create(
            nombre="Chofer", dni="11111111", telefono="+51900000002", activo=True,
        )

        # Mismo teléfono que un ayudante, pero INACTIVO — no debe contar como Campo.
        self.cliente_ex_ayudante = Cliente.objects.create(nombre="Ex ayudante", telefono="+51900000003")
        self.conv_ex_ayudante = ConversacionWhatsApp.objects.create(cliente=self.cliente_ex_ayudante, channel=self.channel)
        Ayudante.objects.create(
            nombre="Ex ayudante", dni="22222222", telefono="+51900000003", activo=False,
        )

    def _active(self):
        r = self.client.get("/dashboard/whatsapp/conversaciones/api/active/")
        return {c["id"]: c for c in r.json()["conversations"]}

    def test_campo_se_autodetecta_por_telefono_de_conductor_activo(self):
        data = self._active()
        self.assertTrue(data[self.conv_conductor.id]["is_campo"])
        self.assertFalse(data[self.conv_conductor.id]["is_oficina"])

    def test_ayudante_inactivo_no_cuenta_como_campo(self):
        data = self._active()
        self.assertFalse(data[self.conv_ex_ayudante.id]["is_campo"])

    def test_cliente_regular_no_es_oficina_ni_campo(self):
        data = self._active()
        row = data[self.conv_regular.id]
        self.assertFalse(row["is_campo"])
        self.assertFalse(row["is_oficina"])

    def test_transportistas_all_trae_regulares_y_transportistas_juntos(self):
        self.cliente_regular.es_transportista = True
        self.cliente_regular.save(update_fields=["es_transportista"])

        # default: excluye al transportista
        default = self._active()
        self.assertNotIn(self.conv_regular.id, default)

        # ?transportistas=all: lo trae junto con los demás (partición client-side)
        r = self.client.get("/dashboard/whatsapp/conversaciones/api/active/?transportistas=all")
        all_ids = {c["id"] for c in r.json()["conversations"]}
        self.assertIn(self.conv_regular.id, all_ids)
        self.assertIn(self.conv_conductor.id, all_ids)

    def test_marcar_oficina_a_mano(self):
        r = self.client.post(
            f"/dashboard/whatsapp/conversaciones/{self.conv_regular.id}/oficina/",
            data=json.dumps({"es_oficina": True}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["es_oficina"])
        self.cliente_regular.refresh_from_db()
        self.assertTrue(self.cliente_regular.es_oficina)

        data = self._active()
        self.assertTrue(data[self.conv_regular.id]["is_oficina"])

    def test_desmarcar_oficina(self):
        self.cliente_regular.es_oficina = True
        self.cliente_regular.save(update_fields=["es_oficina"])
        r = self.client.post(
            f"/dashboard/whatsapp/conversaciones/{self.conv_regular.id}/oficina/",
            data=json.dumps({"es_oficina": False}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["es_oficina"])

    def test_marcar_campo_a_mano_refuerza_la_deteccion_automatica(self):
        r = self.client.post(
            f"/dashboard/whatsapp/conversaciones/{self.conv_regular.id}/campo/",
            data=json.dumps({"es_campo": True}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["es_campo"])
        self.cliente_regular.refresh_from_db()
        self.assertTrue(self.cliente_regular.es_campo)

        data = self._active()
        self.assertTrue(data[self.conv_regular.id]["is_campo"])

    def test_desmarcar_campo_manual_no_afecta_la_deteccion_automatica(self):
        # El conductor sigue siendo Campo por teléfono aunque el flag manual
        # esté en False — las dos vías son un OR, no se pisan entre sí.
        r = self.client.post(
            f"/dashboard/whatsapp/conversaciones/{self.conv_conductor.id}/campo/",
            data=json.dumps({"es_campo": False}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        data = self._active()
        self.assertTrue(data[self.conv_conductor.id]["is_campo"])
