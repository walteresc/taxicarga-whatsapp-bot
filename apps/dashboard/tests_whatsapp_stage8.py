from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.whatsapp.models import ConfiguracionBot, WhatsAppChannel


class WhatsAppBotConfigurationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        admin_group, _ = Group.objects.get_or_create(name="Administrador")
        advisor_group, _ = Group.objects.get_or_create(name="Asesor de Ventas")
        cls.admin = users.objects.create_user("config_admin", password="x")
        cls.advisor = users.objects.create_user("config_advisor", password="x")
        cls.admin.groups.add(admin_group)
        cls.advisor.groups.add(advisor_group)
        cls.channel = WhatsAppChannel.objects.create(
            nombre="Canal Config Stage8", phone_number_id="stage8-phone-id", numero_visible="+51 900 888 888"
        )
        cls.config = ConfiguracionBot.objects.create(channel=cls.channel, modo_atencion="mixto", modo_operacion="hibrido")

    @property
    def url(self):
        return reverse("dashboard-whatsapp-configuracion")

    def _payload(self, **updates):
        data = {
            "channel_id": str(self.channel.id),
            "modo_operacion": "recopilar",
            "hora_inicio_bot": "07:00",
            "hora_fin_bot": "21:00",
            "zona_horaria": "America/Lima",
            "confianza_minima": "82",
            "margen_minimo_porcentaje": "25",
            "espera_asesor_minutos": "20",
            "seguimiento_horas": "48",
            "asesor_predeterminado": str(self.advisor.id),
            "transferir_fuera_horario": "1",
            "lunes_activo": "1",
            "martes_activo": "1",
            "reglas_automaticas": ["provincia", "objetos_especiales"],
            "mensaje_bienvenida": "Hola desde TaxiCarga",
            "mensaje_fuera_horario": "Te atenderemos pronto",
        }
        data.update(updates)
        return data

    def test_admin_sees_channels_and_four_modes(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"channel": self.channel.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Canal Config Stage8")
        self.assertContains(response, "Solo asesor")
        self.assertContains(response, "Recopilar datos")
        self.assertContains(response, "Cotización automática")
        self.assertContains(response, "Híbrido")

    def test_advisor_cannot_open_configuration(self):
        self.client.force_login(self.advisor)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_save_updates_rules_and_maps_legacy_mode(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.modo_operacion, "recopilar")
        self.assertEqual(self.config.modo_atencion, "bot")
        self.assertTrue(self.config.bot_activo)
        self.assertEqual(self.config.confianza_minima, 82)
        self.assertEqual(self.config.margen_minimo_porcentaje, 25)
        self.assertEqual(self.config.reglas_automaticas, ["provincia", "objetos_especiales"])
        self.assertEqual(self.config.asesor_predeterminado, self.advisor)
        self.assertFalse(self.config.domingo_activo)

    def test_solo_advisor_disables_legacy_bot(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self._payload(modo_operacion="asesor"))
        self.config.refresh_from_db()
        self.assertEqual(self.config.modo_atencion, "humano")
        self.assertFalse(self.config.bot_activo)

    def test_invalid_confidence_does_not_update(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self._payload(confianza_minima="120"))
        self.assertEqual(response.status_code, 200)
        self.config.refresh_from_db()
        self.assertEqual(self.config.modo_operacion, "hibrido")
        self.assertContains(response, "Confianza mínima debe estar entre 0 y 100")

    def test_legacy_api_exposes_and_syncs_operating_mode(self):
        self.client.force_login(self.admin)
        get_response = self.client.get("/api/bot-settings/", {"channel": self.channel.id})
        self.assertEqual(get_response.json()["modo_operacion"], "hibrido")
        patch_response = self.client.patch(
            f"/api/bot-settings/?channel={self.channel.id}",
            {"modo_atencion": "humano", "bot_activo": False},
            content_type="application/json",
        )
        self.assertEqual(patch_response.status_code, 200)
        self.config.refresh_from_db()
        self.assertEqual(self.config.modo_operacion, "asesor")
