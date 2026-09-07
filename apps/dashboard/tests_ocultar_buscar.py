"""'Ocultar' una conversación (archivarla) no debe volverla imposible de
encontrar: buscar desde la bandeja principal alcanza también a las
archivadas, y crear una conversación manual para ese mismo número la trae
de vuelta (mismo reset que un mensaje entrante nuevo, ver services_ycloud.py)."""
import json

from django.contrib.auth.models import Group, User
from django.test import TestCase

from apps.whatsapp.domain import crear_conversacion_manual
from apps.whatsapp.models import WhatsAppChannel


class OcultarBuscarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("asesor_ocultar", password="x")
        g, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        self.user.groups.add(g)
        self.client.force_login(self.user)

        self.channel = WhatsAppChannel.objects.create(
            nombre="Canal test", phone_number_id="test-ocultar-buscar", activo=True,
        )
        self.conv = crear_conversacion_manual("+51900777001", self.user, nombre="Contacto Oculto")
        self.conv.archivada = True
        self.conv.save(update_fields=["archivada"])

    def test_bandeja_principal_sin_busqueda_no_trae_archivadas(self):
        r = self.client.get("/dashboard/whatsapp/conversaciones/api/active/")
        ids = [c["id"] for c in r.json()["conversations"]]
        self.assertNotIn(self.conv.id, ids)

    def test_buscar_desde_bandeja_principal_encuentra_archivadas(self):
        r = self.client.get("/dashboard/whatsapp/conversaciones/api/active/?q=900777001")
        ids = [c["id"] for c in r.json()["conversations"]]
        self.assertIn(self.conv.id, ids)

    def test_pestana_archivados_no_se_ve_afectada_por_la_busqueda(self):
        r = self.client.get("/dashboard/whatsapp/conversaciones/api/active/?archived=true&q=900777001")
        ids = [c["id"] for c in r.json()["conversations"]]
        self.assertIn(self.conv.id, ids)

    def test_crear_conversacion_manual_desarchiva_el_contacto_existente(self):
        r = self.client.post(
            "/dashboard/whatsapp/conversaciones/nueva/",
            data=json.dumps({"telefono": "+51900777001"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["conversation_id"], self.conv.id)
        self.conv.refresh_from_db()
        self.assertFalse(self.conv.archivada)
