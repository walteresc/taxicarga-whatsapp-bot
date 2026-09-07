from unittest.mock import patch

from django.test import TestCase

from apps.clientes.models import Cliente
from apps.cotizador.models import SolicitudCotizacion
from apps.cotizador.pipeline import sync_review_request
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp.services_extraccion import (
    MOTIVOS_INTERVENCION_HUMANA,
    _normalizar_extraccion,
    extraer_datos_conversacion,
    hay_intencion_de_cotizar,
    requiere_intervencion_humana,
    volcar_datos_extraidos_al_lead,
)
from apps.whatsapp_bot_v4.models import BotGlobalConfig


class NormalizacionSenalesTests(TestCase):
    def test_detecta_cada_senal_individualmente(self):
        for campo_raw, campo_out in (
            ("quiere_hablar_con_asesor", "quiere_asesor"),
            ("pide_precio_sin_dar_datos", "pide_precio_sin_datos"),
            ("no_responde_preguntas_del_bot", "no_responde_preguntas"),
            ("carga_dificil_de_cotizar", "carga_compleja"),
        ):
            out = _normalizar_extraccion({campo_raw: True})
            self.assertTrue(out.get(campo_out), f"no detectó {campo_raw}")

    def test_false_no_marca_senal(self):
        out = _normalizar_extraccion({"quiere_hablar_con_asesor": False})
        self.assertNotIn("quiere_asesor", out)

    def test_sin_senales_no_requiere_intervencion(self):
        out = _normalizar_extraccion({"tipo_servicio": "Mudanza"})
        self.assertFalse(requiere_intervencion_humana(out))

    def test_una_senal_activa_requiere_intervencion(self):
        out = _normalizar_extraccion({"pide_precio_sin_dar_datos": True})
        self.assertTrue(requiere_intervencion_humana(out))


class PrecioChatTests(TestCase):
    def test_captura_precio_negociado(self):
        out = _normalizar_extraccion({
            "precio_acordado": "S/ 1200",
            "precio_aceptado_por_cliente": True,
            "precio_incluye": "transporte y personal",
            "precio_condiciones": "50% y 50%",
        })
        self.assertEqual(out["precio_chat"], 1200.0)
        self.assertTrue(out["precio_chat_aceptado"])
        self.assertEqual(out["precio_chat_incluye"], "transporte y personal")
        self.assertEqual(out["precio_chat_condiciones"], "50% y 50%")

    def test_precio_chat_no_se_vuelca_al_lead(self):
        out = _normalizar_extraccion({"precio_acordado": 900})
        self.assertEqual(out["precio_chat"], 900.0)
        self.assertNotIn("precio_chat_aceptado", out)

    def test_sin_precio_no_agrega_claves(self):
        out = _normalizar_extraccion({"tipo_servicio": "mudanza"})
        self.assertNotIn("precio_chat", out)


class VolcadoIntervencionTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre="Juan Perez", telefono="+51999111222")
        self.lead = Lead.objects.create(cliente=self.cliente, requiere_asesor=False)

    def test_marca_requiere_asesor_y_motivo(self):
        cambios = volcar_datos_extraidos_al_lead(
            self.lead, {"quiere_asesor": True}, solo_vacios=True
        )
        self.lead.refresh_from_db()
        self.assertIn("requiere_asesor", cambios)
        self.assertIn("motivo_derivacion", cambios)
        self.assertTrue(self.lead.requiere_asesor)
        self.assertIn("Cliente pide hablar con un asesor", self.lead.motivo_derivacion)

    def test_dos_senales_a_la_vez_agregan_motivo_una_sola_vez_en_cambios(self):
        cambios = volcar_datos_extraidos_al_lead(
            self.lead,
            {"quiere_asesor": True, "carga_compleja": True},
            solo_vacios=True,
        )
        self.assertEqual(cambios.count("motivo_derivacion"), 1)
        self.lead.refresh_from_db()
        self.assertIn("Cliente pide hablar con un asesor", self.lead.motivo_derivacion)
        self.assertIn("Carga atípica", self.lead.motivo_derivacion)

    def test_segunda_pasada_es_idempotente(self):
        datos = {"quiere_asesor": True}
        volcar_datos_extraidos_al_lead(self.lead, datos, solo_vacios=True)
        self.lead.refresh_from_db()
        motivo_tras_primera = self.lead.motivo_derivacion

        cambios_segunda = volcar_datos_extraidos_al_lead(self.lead, datos, solo_vacios=True)
        self.lead.refresh_from_db()
        self.assertEqual(cambios_segunda, [])
        self.assertEqual(self.lead.motivo_derivacion, motivo_tras_primera)

    def test_no_pisa_motivo_derivacion_existente_del_asesor(self):
        self.lead.motivo_derivacion = "Nota del asesor: llamar mañana"
        self.lead.save(update_fields=["motivo_derivacion"])
        volcar_datos_extraidos_al_lead(self.lead, {"quiere_asesor": True}, solo_vacios=True)
        self.lead.refresh_from_db()
        self.assertIn("Nota del asesor: llamar mañana", self.lead.motivo_derivacion)
        self.assertIn("Cliente pide hablar con un asesor", self.lead.motivo_derivacion)

    def test_sin_senales_no_cambia_nada(self):
        cambios = volcar_datos_extraidos_al_lead(self.lead, {}, solo_vacios=True)
        self.assertEqual(cambios, [])
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.requiere_asesor)


class IntencionCotizarTests(TestCase):
    """Señal `quiere_cotizar`: crea el Lead antes de completar el umbral y lo deja
    en 'Oportunidades' (no en 'Para revisión')."""

    def test_normaliza_la_senal(self):
        out = _normalizar_extraccion({"quiere_cotizar": True})
        self.assertIs(out.get("quiere_cotizar"), True)
        self.assertTrue(hay_intencion_de_cotizar(out))

    def test_sin_senal_no_hay_intencion(self):
        self.assertFalse(hay_intencion_de_cotizar(_normalizar_extraccion({"tipo_servicio": "mudanza"})))

    def test_intencion_no_es_intervencion_humana(self):
        out = _normalizar_extraccion({"quiere_cotizar": True})
        self.assertFalse(requiere_intervencion_humana(out))

    @patch("apps.whatsapp.services_extraccion._llamar_openai")
    def test_crea_lead_en_oportunidades_sin_datos_completos(self, mock_openai):
        from apps.cotizador.pipeline import potenciales_queryset

        mock_openai.return_value = {"quiere_cotizar": True}
        cliente = Cliente.objects.create(nombre="Rosa Díaz", telefono="+51988000111")
        conv = ConversacionWhatsApp.objects.create(cliente=cliente)
        MensajeWhatsApp.objects.create(
            conversacion=conv, direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            contenido="Hola, quiero cotizar una mudanza",
        )

        reporte = extraer_datos_conversacion(conv)

        self.assertEqual(reporte["lead_accion"], "lead creado (intención de cotizar)")
        conv.refresh_from_db()
        lead = conv.lead
        self.assertIsNotNone(lead)
        self.assertFalse(lead.requiere_asesor)
        self.assertEqual(SolicitudCotizacion.objects.filter(lead=lead).count(), 0)
        self.assertIn("intencion_cotizar", lead.nota_interna or "")
        self.assertIn(lead.id, list(potenciales_queryset().values_list("id", flat=True)))

    @patch("apps.whatsapp.services_extraccion._llamar_openai")
    def test_si_ademas_pide_precio_sin_datos_va_a_revision(self, mock_openai):
        mock_openai.return_value = {"quiere_cotizar": True, "pide_precio_sin_dar_datos": True}
        cliente = Cliente.objects.create(nombre="Beto Luna", telefono="+51988000222")
        conv = ConversacionWhatsApp.objects.create(cliente=cliente)
        MensajeWhatsApp.objects.create(
            conversacion=conv, direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            contenido="cuánto cuesta? dime el precio ya",
        )

        reporte = extraer_datos_conversacion(conv)

        self.assertEqual(reporte["lead_accion"], "lead creado")
        conv.refresh_from_db()
        self.assertTrue(conv.lead.requiere_asesor)


class BotOperativoPausadoTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre="Luis Rojas", telefono="+51999333444")
        self.lead = Lead.objects.create(cliente=self.cliente)
        from apps.whatsapp.domain import obtener_o_crear_conversacion
        self.conversacion = obtener_o_crear_conversacion(self.lead)
        MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            contenido="Hola, quiero cotizar una mudanza",
        )

    @patch("apps.whatsapp.services_extraccion._llamar_openai")
    def test_operativo_pausado_no_llama_a_openai_ni_procesa(self, mock_openai):
        BotGlobalConfig.objects.create(operativo_paused=True)
        reporte = extraer_datos_conversacion(self.conversacion)
        mock_openai.assert_not_called()
        self.assertEqual(reporte["error"], "bot operativo pausado — barrido detenido")
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.datos_extraidos or {}, {})

    @patch("apps.whatsapp.services_extraccion._llamar_openai")
    def test_operativo_activo_si_llama_a_openai(self, mock_openai):
        mock_openai.return_value = {"tipo_servicio": "Mudanza"}
        BotGlobalConfig.objects.create(operativo_paused=False)
        extraer_datos_conversacion(self.conversacion)
        mock_openai.assert_called_once()

    @patch("apps.whatsapp.services_extraccion._llamar_openai")
    def test_sin_config_no_bloquea(self, mock_openai):
        # No existe fila BotGlobalConfig todavía (caso limpio / fresh install).
        mock_openai.return_value = {"tipo_servicio": "Mudanza"}
        extraer_datos_conversacion(self.conversacion)
        mock_openai.assert_called_once()


class SyncReviewRequestRefrescaMotivoTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre="Ana Gomez", telefono="+51999222333")

    def test_solicitud_activa_refresca_motivo_con_senal_nueva(self):
        lead = Lead.objects.create(
            cliente=self.cliente, requiere_asesor=True, motivo_derivacion="Carga atípica"
        )
        solicitud = sync_review_request(lead)
        self.assertIsNotNone(solicitud)
        self.assertIn("Carga atípica", solicitud.motivo)

        volcar_datos_extraidos_al_lead(lead, {"quiere_asesor": True}, solo_vacios=True)
        lead.refresh_from_db()

        resultado = sync_review_request(lead)
        self.assertIsNone(resultado, "no debe crear una segunda solicitud")
        solicitud.refresh_from_db()
        self.assertIn("Cliente pide hablar con un asesor", solicitud.motivo)
        self.assertEqual(
            SolicitudCotizacion.objects.filter(lead=lead).count(), 1,
            "sigue siendo una sola solicitud, solo se actualizó el motivo",
        )
