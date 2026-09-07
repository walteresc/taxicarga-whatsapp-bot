"""Mensajes predefinidos del rayo del composer — propios de cada asesor."""
import json

from django.contrib.auth.models import Group, User
from django.test import TestCase

from apps.whatsapp.models import RespuestaRapida, WhatsAppChannel


class RespuestasRapidasTests(TestCase):
    URL = "/dashboard/whatsapp/respuestas-rapidas/"

    def setUp(self):
        self.user = User.objects.create_user("asesor_rr", password="x")
        g, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        self.user.groups.add(g)
        self.client.force_login(self.user)
        WhatsAppChannel.objects.get_or_create(phone_number_id="rr-test", defaults={"nombre": "c", "activo": True})

    def test_get_siembra_los_default_la_primera_vez(self):
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 200)
        items = r.json()["items"]
        self.assertGreater(len(items), 0)
        self.assertEqual(RespuestaRapida.objects.filter(usuario=self.user).count(), len(items))

    def test_post_reemplaza_toda_la_lista(self):
        self.client.get(self.URL)  # siembra
        r = self.client.post(
            self.URL,
            data=json.dumps({"items": ["Hola", "  ", "Chau", "Hola"]}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["items"], ["Hola", "Chau", "Hola"])
        self.assertEqual(
            list(RespuestaRapida.objects.filter(usuario=self.user).order_by("orden").values_list("texto", flat=True)),
            ["Hola", "Chau", "Hola"],
        )

    def test_son_por_usuario(self):
        self.client.post(self.URL, data=json.dumps({"items": ["mío"]}), content_type="application/json")
        otro = User.objects.create_user("otro_rr", password="x")
        otro.groups.add(Group.objects.get(name="Asesor de Ventas"))
        self.client.force_login(otro)
        r = self.client.get(self.URL)
        self.assertNotIn("mío", r.json()["items"])
