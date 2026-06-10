from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.management import call_command
from django.utils import timezone
from datetime import datetime, timedelta
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from apps.clientes.models import Cliente, Conversacion
from apps.leads.models import Lead
from apps.whatsapp.services import send_whatsapp_message
from apps.whatsapp.models import EvidenciaWhatsapp
from apps.whatsapp.models import MensajeWhatsappProcesado
from apps.whatsapp.models import BotSchedule, ConfiguracionBot, WhatsAppChannel
from apps.whatsapp.services import download_whatsapp_image
from apps.whatsapp.utils import should_bot_reply, should_bot_handle_lead, evaluar_mixto_inteligente


class ShouldBotReplyTests(TestCase):
    def setUp(self):
        self.conf = ConfiguracionBot.obtener()

    def _hora(self, h, m):
        return timezone.make_aware(
            datetime(2026, 6, 9, h, m),
            timezone.get_current_timezone(),
        )

    def test_bot_activo_dentro_horario(self):
        self.conf.bot_activo = True
        self.conf.hora_inicio_bot = "09:00"
        self.conf.hora_fin_bot = "18:00"
        self.conf.lunes_activo = True
        self.conf.save()
        ahora = self._hora(14, 30)
        self.assertTrue(should_bot_reply(now=ahora))

    def test_bot_activo_fuera_horario(self):
        self.conf.bot_activo = True
        self.conf.hora_inicio_bot = "09:00"
        self.conf.hora_fin_bot = "18:00"
        self.conf.lunes_activo = True
        self.conf.save()
        ahora = self._hora(20, 0)
        self.assertFalse(should_bot_reply(now=ahora))

    def test_bot_apagado(self):
        self.conf.bot_activo = False
        self.conf.save()
        ahora = self._hora(14, 30)
        self.assertFalse(should_bot_reply(now=ahora))

    def test_domingo_apagado(self):
        self.conf.bot_activo = True
        self.conf.lunes_activo = True
        self.conf.domingo_activo = False
        self.conf.save()
        domingo = timezone.make_aware(
            datetime(2026, 6, 7, 14, 0),
            timezone.get_current_timezone(),
        )
        self.assertFalse(should_bot_reply(now=domingo))

    def test_horario_cruza_medianoche_dentro(self):
        self.conf.bot_activo = True
        self.conf.hora_inicio_bot = "19:00"
        self.conf.hora_fin_bot = "08:00"
        self.conf.lunes_activo = True
        self.conf.save()
        ahora = self._hora(22, 0)
        self.assertTrue(should_bot_reply(now=ahora))

    def test_horario_cruza_medianoche_fuera(self):
        self.conf.bot_activo = True
        self.conf.hora_inicio_bot = "19:00"
        self.conf.hora_fin_bot = "08:00"
        self.conf.lunes_activo = True
        self.conf.save()
        ahora = self._hora(10, 0)
        self.assertFalse(should_bot_reply(now=ahora))

    def test_modo_humano(self):
        self.conf.bot_activo = True
        self.conf.modo_atencion = "humano"
        self.conf.save()
        ahora = self._hora(14, 30)
        self.assertFalse(should_bot_reply(now=ahora))

    def test_modo_mixto(self):
        self.conf.bot_activo = True
        self.conf.modo_atencion = "mixto"
        self.conf.save()
        ahora = self._hora(14, 30)
        self.assertTrue(should_bot_reply(now=ahora))


class BotSettingsAPITests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username="test", password="pass")
        self.conf = ConfiguracionBot.obtener()

    def test_get_requiere_auth(self):
        response = self.client.get("/api/bot-settings/")
        self.assertEqual(response.status_code, 403)

    def test_get_returns_config(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/bot-settings/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("bot_activo", data)
        self.assertIn("modo_atencion", data)
        self.assertIn("hora_inicio_bot", data)
        self.assertIn("dias_semana", data)

    def test_patch_updates_config(self):
        self.client.force_login(self.user)
        response = self.client.patch(
            "/api/bot-settings/",
            {"bot_activo": False, "modo_atencion": "humano"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.conf.refresh_from_db()
        self.assertFalse(self.conf.bot_activo)
        self.assertEqual(self.conf.modo_atencion, "humano")


class IntegrationBotConfigWebhookTests(TestCase):
    @override_settings(OPENAI_API_KEY="")
    @patch("apps.whatsapp.views.send_whatsapp_message")
    def test_bot_apagado_marca_lead_como_humano(self, send_mock):
        conf = ConfiguracionBot.obtener()
        conf.bot_activo = False
        conf.save()
        send_mock.return_value = {"messages": [{"id": "wamid.reply"}]}
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "51988888888",
                                        "id": "wamid.bot-off-1",
                                        "type": "text",
                                        "text": {"body": "Hola, quiero informacion"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        response = self.client.post(
            reverse("whatsapp-webhook"),
            payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["human_takeover"])
        lead = Lead.objects.filter(cliente__telefono="51988888888").first()
        self.assertIsNotNone(lead)
        self.assertTrue(lead.atencion_humana)
        send_mock.assert_not_called()

    @override_settings(OPENAI_API_KEY="")
    @patch("apps.whatsapp.views.send_whatsapp_message")
    def test_fuera_horario_marca_lead_como_humano(self, send_mock):
        conf = ConfiguracionBot.obtener()
        conf.bot_activo = True
        conf.hora_inicio_bot = "09:00"
        conf.hora_fin_bot = "18:00"
        conf.lunes_activo = True
        conf.save()
        send_mock.return_value = {"messages": [{"id": "wamid.reply"}]}
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "51999999999",
                                        "id": "wamid.after-hours-1",
                                        "type": "text",
                                        "text": {"body": "Consulta fuera de horario"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        response = self.client.post(
            reverse("whatsapp-webhook"),
            payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["human_takeover"])
        send_mock.assert_not_called()


class WhatsappWebhookTests(TestCase):
    def setUp(self):
        conf = ConfiguracionBot.obtener()
        conf.hora_inicio_bot = "00:00"
        conf.hora_fin_bot = "23:59"
        conf.save()

    @override_settings(WHATSAPP_VERIFY_TOKEN="token-test")
    def test_valida_webhook_get(self):
        response = self.client.get(
            reverse("whatsapp-webhook"),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "token-test",
                "hub.challenge": "abc123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "abc123")

    @override_settings(OPENAI_API_KEY="")
    @patch("apps.whatsapp.views.send_whatsapp_message")
    def test_conversation_flow(self, send_mock):
        # Escenario básico de conversación
        send_mock.return_value = {"messages": [{"id": "wamid.reply"}]}
        client_phone = "51955555555"

        def send_message(message):
            payload = {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "messages": [
                                        {
                                            "from": client_phone,
                                            "text": {"body": message},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }

            response = self.client.post(
                reverse("whatsapp-webhook"),
                payload,
                content_type="application/json",
            )
            return response

        messages_to_test = [
            "Hola",
            "Quiero cotizar un traslado",
            "El origen y el destino es por ascensor",
            "Confirmo la fecha",
            "Gracias"
        ]

        for msg in messages_to_test:
            response = send_message(msg)
            self.assertEqual(response.status_code, 200)

        self.assertTrue(Cliente.objects.filter(telefono=client_phone).exists())
        self.assertTrue(Conversacion.objects.filter(cliente__telefono=client_phone).exists())

        # Se comprueba que la función de envío fue llamada al menos una vez
        self.assertTrue(send_mock.called)

    @override_settings(OPENAI_API_KEY="")
    @patch("apps.whatsapp.views.send_whatsapp_message")
    def test_recibe_mensaje_post_y_guarda_conversacion(self, send_mock):
        send_mock.return_value = {"messages": [{"id": "wamid.reply"}]}
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "51955555555",
                                        "text": {"body": "Hola, quiero una mudanza"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        response = self.client.post(
            reverse("whatsapp-webhook"),
            payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Cliente.objects.filter(telefono="51955555555").exists())
        self.assertEqual(Conversacion.objects.count(), 1)
        send_mock.assert_called_once()

    @override_settings(OPENAI_API_KEY="")
    @patch("apps.whatsapp.views.send_whatsapp_message")
    def test_no_consume_mensaje_si_meta_rechaza_la_respuesta(self, send_mock):
        send_mock.return_value = {
            "sent": False,
            "reason": "request_error",
            "status_code": 401,
            "error_code": 190,
            "error_subcode": 463,
        }
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "51955556666",
                                        "id": "wamid.failed-send",
                                        "type": "text",
                                        "text": {"body": "Hola"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        response = self.client.post(
            reverse("whatsapp-webhook"),
            payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(Conversacion.objects.count(), 0)
        self.assertFalse(
            MensajeWhatsappProcesado.objects.filter(
                message_id="wamid.failed-send"
            ).exists()
        )

    @override_settings(OPENAI_API_KEY="")
    @patch("apps.whatsapp.views.send_whatsapp_message")
    def test_no_responde_auto_si_lead_esta_en_atencion_humana(self, send_mock):
        cliente = Cliente.objects.create(telefono="51955550000")
        Lead.objects.create(cliente=cliente, estado=Lead.ASIGNADO, atencion_humana=True)
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "51955550000",
                                        "text": {"body": "Me confirma la hora por favor?"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        response = self.client.post(
            reverse("whatsapp-webhook"),
            payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["human_takeover"])
        self.assertEqual(Conversacion.objects.count(), 1)
        self.assertEqual(Conversacion.objects.first().mensaje_salida, "")
        send_mock.assert_not_called()

    @patch("apps.whatsapp.views.analyze_moving_image")
    @patch("apps.whatsapp.views.download_whatsapp_image")
    @patch("apps.whatsapp.views.send_whatsapp_message")
    def test_recibe_imagen_detecta_objetos_y_continua_flujo(
        self,
        send_mock,
        download_mock,
        analyze_mock,
    ):
        send_mock.return_value = {"messages": [{"id": "wamid.reply"}]}
        evidence = EvidenciaWhatsapp.objects.create(
            cliente=Cliente.objects.create(telefono="51955551111"),
            media_id="media-test-evidence",
            archivo="whatsapp/test.jpg",
            mime_type="image/jpeg",
        )
        download_mock.return_value = {"saved": True, "evidence": evidence}
        analyze_mock.return_value = {
            "objetos": ["un escritorio", "una silla", "una PC"],
            "objetos_pesados": [],
            "resumen": "un escritorio, una silla y una PC",
        }
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "51955551111",
                                        "id": "wamid.image-1",
                                        "type": "image",
                                        "image": {
                                            "id": "media-123",
                                            "mime_type": "image/jpeg",
                                            "sha256": "abc",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        response = self.client.post(
            reverse("whatsapp-webhook"),
            payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["media_saved"])
        self.assertEqual(Conversacion.objects.count(), 1)
        self.assertIn("Foto recibida", Conversacion.objects.first().mensaje_entrada)
        self.assertIn("escritorio", Conversacion.objects.first().mensaje_salida)
        lead = Cliente.objects.get(telefono="51955551111").leads.first()
        self.assertIn("escritorio", lead.lista_objetos)
        send_mock.assert_called_once()

    @override_settings(OPENAI_API_KEY="")
    @patch("apps.whatsapp.views.send_whatsapp_message")
    def test_no_procesa_dos_veces_el_mismo_mensaje(self, send_mock):
        send_mock.return_value = {"messages": [{"id": "wamid.reply"}]}
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "51955553333",
                                        "id": "wamid.incoming-duplicate",
                                        "type": "text",
                                        "text": {"body": "Hola, quiero una mudanza"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        first = self.client.post(
            reverse("whatsapp-webhook"),
            payload,
            content_type="application/json",
        )
        second = self.client.post(
            reverse("whatsapp-webhook"),
            payload,
            content_type="application/json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(Conversacion.objects.count(), 1)
        self.assertEqual(MensajeWhatsappProcesado.objects.count(), 1)
        self.assertTrue(MensajeWhatsappProcesado.objects.first().completado)
        send_mock.assert_called_once()

    @patch("apps.whatsapp.views.download_whatsapp_image")
    @patch("apps.whatsapp.views.send_whatsapp_message")
    def test_no_descarga_dos_veces_la_misma_imagen(self, send_mock, download_mock):
        send_mock.return_value = {"messages": [{"id": "wamid.reply"}]}
        download_mock.return_value = {"saved": True}
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "51955554444",
                                        "id": "wamid.image-duplicate",
                                        "type": "image",
                                        "image": {
                                            "id": "media-duplicate",
                                            "mime_type": "image/jpeg",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        self.client.post(
            reverse("whatsapp-webhook"),
            payload,
            content_type="application/json",
        )
        duplicate = self.client.post(
            reverse("whatsapp-webhook"),
            payload,
            content_type="application/json",
        )

        self.assertTrue(duplicate.json()["duplicate"])
        download_mock.assert_called_once()
        send_mock.assert_called_once()

    @override_settings(OPENAI_API_KEY="")
    @patch("apps.whatsapp.views.download_whatsapp_image")
    @patch("apps.whatsapp.views.send_whatsapp_message")
    def test_foto_nueva_no_reutiliza_cotizacion_anterior(
        self,
        send_mock,
        download_mock,
    ):
        send_mock.return_value = {"messages": [{"id": "wamid.reply"}]}
        download_mock.return_value = {"saved": False, "reason": "test"}
        cliente = Cliente.objects.create(telefono="51955557777")
        old_lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            piso_origen=2,
            piso_destino=2,
            ascensor_origen=True,
            ascensor_destino=False,
            camion_llega_origen=True,
            camion_llega_destino=True,
            lista_objetos="cama y refrigeradora",
            incluye_personal_carga=True,
            modalidad_servicio="sin embalaje",
            requiere_desarmado=False,
            fecha_por_confirmar=True,
            estado=Lead.COTIZADO,
            precio_recomendado="350.00",
        )
        conversation = Conversacion.objects.create(
            cliente=cliente,
            mensaje_entrada="Servicio anterior",
            mensaje_salida="Cotizacion anterior",
            canal=Conversacion.CANAL_WHATSAPP,
        )
        Conversacion.objects.filter(pk=conversation.pk).update(
            fecha=timezone.now() - timedelta(hours=2)
        )
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": cliente.telefono,
                                        "id": "wamid.new-quote-image",
                                        "type": "image",
                                        "image": {
                                            "id": "media-new-quote",
                                            "mime_type": "image/jpeg",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        response = self.client.post(
            reverse("whatsapp-webhook"),
            payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(cliente.leads.count(), 2)
        new_lead = cliente.leads.exclude(pk=old_lead.pk).get()
        self.assertEqual(new_lead.distrito_origen, "")
        self.assertEqual(new_lead.distrito_destino, "")
        self.assertIn(
            "que deseas trasladar",
            Conversacion.objects.order_by("-id").first().mensaje_salida.lower(),
        )

    @override_settings(
        WHATSAPP_ACCESS_TOKEN="token",
        WHATSAPP_API_VERSION="v25.0",
    )
    @patch("apps.whatsapp.services.requests.get")
    def test_descarga_imagen_privada_y_evitar_duplicados(self, get_mock):
        cliente = Cliente.objects.create(telefono="51955552222")
        lead = Lead.objects.create(cliente=cliente)
        metadata_response = get_mock.return_value
        media_response = type(metadata_response)()
        metadata_response.raise_for_status.return_value = None
        metadata_response.json.return_value = {
            "url": "https://lookaside.example/media",
            "mime_type": "image/jpeg",
            "sha256": "hash-meta",
        }
        media_response.raise_for_status.return_value = None
        media_response.content = b"fake-jpeg-bytes"
        get_mock.side_effect = [metadata_response, media_response]
        event = {
            "media_id": "media-private-1",
            "mime_type": "image/jpeg",
            "sha256": "hash-event",
            "caption": "Sofa y cajas",
        }

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            result = download_whatsapp_image(cliente, lead, event)
            duplicate = download_whatsapp_image(cliente, lead, event)

            self.assertTrue(result["saved"])
            self.assertTrue(duplicate["duplicate"])
            evidence = EvidenciaWhatsapp.objects.get(media_id="media-private-1")
            self.assertTrue(evidence.archivo.name.endswith(".jpg"))
            self.assertEqual(evidence.caption, "Sofa y cajas")
            self.assertEqual(EvidenciaWhatsapp.objects.count(), 1)

    @override_settings(
        WHATSAPP_ACCESS_TOKEN="token",
        WHATSAPP_PHONE_NUMBER_ID="123456",
        WHATSAPP_API_VERSION="v99.0",
    )
    @patch("apps.whatsapp.services.requests.post")
    def test_envio_whatsapp_usa_version_configurable(self, post_mock):
        post_mock.return_value.raise_for_status.return_value = None
        post_mock.return_value.json.return_value = {"messages": [{"id": "wamid.test"}]}

        result = send_whatsapp_message("51955555555", "Hola")

        self.assertEqual(result["messages"][0]["id"], "wamid.test")
        self.assertEqual(
            post_mock.call_args.args[0],
            "https://graph.facebook.com/v99.0/123456/messages",
        )

    @override_settings(
        WHATSAPP_VERIFY_TOKEN="verify",
        WHATSAPP_ACCESS_TOKEN="",
        WHATSAPP_PHONE_NUMBER_ID="",
        WHATSAPP_API_VERSION="v20.0",
    )
    def test_diagnostico_whatsapp_muestra_faltantes(self):
        output = StringIO()

        call_command(
            "diagnosticar_whatsapp",
            "--public-url",
            "https://demo.ngrok-free.app",
            stdout=output,
        )

        content = output.getvalue()
        self.assertIn("WHATSAPP_VERIFY_TOKEN", content)
        self.assertIn("WHATSAPP_ACCESS_TOKEN", content)
        self.assertIn("https://demo.ngrok-free.app/webhook/whatsapp/", content)


class AdvancedScheduleTests(TestCase):
    def setUp(self):
        self.conf = ConfiguracionBot.obtener()
        self.conf.bot_activo = True
        self.conf.modo_atencion = "bot"
        self.conf.save()

    def _dt(self, y, m, d, h, mi):
        return timezone.make_aware(
            datetime(y, m, d, h, mi),
            timezone.get_current_timezone(),
        )

    def _create_schedule(self, day, start, end, active=True):
        BotSchedule.objects.create(
            day_of_week=day,
            start_time=datetime.strptime(start, "%H:%M").time(),
            end_time=datetime.strptime(end, "%H:%M").time(),
            is_active=active,
        )

    def test_sabado_15_00_responde(self):
        # Sat Jun 6 2026
        self._create_schedule(5, "14:00", "23:59")
        ahora = self._dt(2026, 6, 6, 15, 0)
        self.assertTrue(should_bot_reply(now=ahora))

    def test_domingo_12_00_responde(self):
        # Sun Jun 7 2026
        self._create_schedule(6, "00:00", "23:59")
        ahora = self._dt(2026, 6, 7, 12, 0)
        self.assertTrue(should_bot_reply(now=ahora))

    def test_lunes_07_00_responde(self):
        # Mon Jun 8 2026
        self._create_schedule(0, "00:00", "07:30")
        self._create_schedule(0, "17:30", "23:59")
        ahora = self._dt(2026, 6, 8, 7, 0)
        self.assertTrue(should_bot_reply(now=ahora))

    def test_lunes_08_00_no_responde(self):
        self._create_schedule(0, "00:00", "07:30")
        self._create_schedule(0, "17:30", "23:59")
        ahora = self._dt(2026, 6, 8, 8, 0)
        self.assertFalse(should_bot_reply(now=ahora))

    def test_lunes_18_00_responde(self):
        self._create_schedule(0, "00:00", "07:30")
        self._create_schedule(0, "17:30", "23:59")
        ahora = self._dt(2026, 6, 8, 18, 0)
        self.assertTrue(should_bot_reply(now=ahora))

    def test_miercoles_14_00_no_responde(self):
        # Wed Jun 10 2026
        self._create_schedule(2, "00:00", "07:30")
        self._create_schedule(2, "17:30", "23:59")
        ahora = self._dt(2026, 6, 10, 14, 0)
        self.assertFalse(should_bot_reply(now=ahora))

    def test_miercoles_18_00_responde(self):
        self._create_schedule(2, "00:00", "07:30")
        self._create_schedule(2, "17:30", "23:59")
        ahora = self._dt(2026, 6, 10, 18, 0)
        self.assertTrue(should_bot_reply(now=ahora))

    def test_fuera_horario_force_bot_responde(self):
        self._create_schedule(2, "00:00", "07:30")
        ahora = self._dt(2026, 6, 10, 14, 0)
        self.assertFalse(should_bot_reply(now=ahora))
        self.conf.override_activo = True
        self.conf.override_modo = "force_bot"
        self.conf.save()
        self.assertTrue(should_bot_reply(now=ahora))

    def test_horario_activo_force_human_no_responde(self):
        self._create_schedule(0, "00:00", "23:59")
        ahora = self._dt(2026, 6, 8, 12, 0)
        self.assertTrue(should_bot_reply(now=ahora))
        self.conf.override_activo = True
        self.conf.override_modo = "force_human"
        self.conf.save()
        self.assertFalse(should_bot_reply(now=ahora))

    def test_desactivar_override_vuelve_a_horario(self):
        self._create_schedule(2, "00:00", "23:59")
        ahora = self._dt(2026, 6, 10, 12, 0)
        self.assertTrue(should_bot_reply(now=ahora))
        self.conf.override_activo = True
        self.conf.override_modo = "force_human"
        self.conf.save()
        self.assertFalse(should_bot_reply(now=ahora))
        self.conf.override_activo = False
        self.conf.override_modo = "none"
        self.conf.save()
        self.assertTrue(should_bot_reply(now=ahora))


class BotScheduleAPITests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username="test", password="pass")

    def test_get_requiere_auth(self):
        response = self.client.get("/api/bot-schedules/")
        self.assertEqual(response.status_code, 403)

    def test_get_empty_list(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/bot-schedules/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_create_schedule(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/bot-schedules/",
            {"day_of_week": 0, "start_time": "09:00", "end_time": "18:00"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["day_of_week"], 0)
        self.assertEqual(data["start_time"], "09:00")
        self.assertTrue(data["is_active"])

    def test_create_list_and_delete(self):
        self.client.force_login(self.user)
        self.client.post(
            "/api/bot-schedules/",
            {"day_of_week": 1, "start_time": "08:00", "end_time": "17:00"},
            content_type="application/json",
        )
        list_resp = self.client.get("/api/bot-schedules/")
        self.assertEqual(len(list_resp.json()), 1)
        sched_id = list_resp.json()[0]["id"]
        del_resp = self.client.delete(f"/api/bot-schedules/{sched_id}/")
        self.assertEqual(del_resp.status_code, 204)
        list_resp2 = self.client.get("/api/bot-schedules/")
        self.assertEqual(len(list_resp2.json()), 0)

    def test_patch_schedule(self):
        self.client.force_login(self.user)
        s = BotSchedule.objects.create(
            day_of_week=0,
            start_time=datetime.strptime("09:00", "%H:%M").time(),
            end_time=datetime.strptime("18:00", "%H:%M").time(),
        )
        response = self.client.patch(
            f"/api/bot-schedules/{s.id}/",
            {"start_time": "10:00", "is_active": False},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        s.refresh_from_db()
        self.assertEqual(s.start_time.strftime("%H:%M"), "10:00")
        self.assertFalse(s.is_active)

    def test_delete_not_found(self):
        self.client.force_login(self.user)
        response = self.client.delete("/api/bot-schedules/999/")
        self.assertEqual(response.status_code, 404)


class OverrideAPITests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username="test", password="pass")
        self.conf = ConfiguracionBot.obtener()

    def test_patch_override(self):
        self.client.force_login(self.user)
        response = self.client.patch(
            "/api/bot-settings/",
            {"override_activo": True, "override_modo": "force_human"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.conf.refresh_from_db()
        self.assertTrue(self.conf.override_activo)
        self.assertEqual(self.conf.override_modo, "force_human")

    def test_get_override_fields(self):
        self.client.force_login(self.user)
        self.conf.override_activo = True
        self.conf.override_modo = "force_bot"
        self.conf.save()
        response = self.client.get("/api/bot-settings/")
        data = response.json()
        self.assertTrue(data["override_activo"])
        self.assertEqual(data["override_modo"], "force_bot")

    def test_clear_override(self):
        self.client.force_login(self.user)
        self.conf.override_activo = True
        self.conf.override_modo = "force_human"
        self.conf.save()
        response = self.client.patch(
            "/api/bot-settings/",
            {"override_activo": False, "override_modo": "none"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.conf.refresh_from_db()
        self.assertFalse(self.conf.override_activo)


class MixtoInteligenteTests(TestCase):
    def setUp(self):
        self.conf = ConfiguracionBot.obtener()
        self.conf.modo_atencion = "mixto"
        self.conf.bot_activo = True
        self.conf.hora_inicio_bot = "00:00"
        self.conf.hora_fin_bot = "23:59"
        self.conf.lunes_activo = True
        self.conf.save()
        self.cliente = Cliente.objects.create(
            telefono="999000001", nombre="Test Mixto"
        )
        BotSchedule.objects.create(
            day_of_week=0,  # Monday
            start_time=datetime.strptime("00:00", "%H:%M").time(),
            end_time=datetime.strptime("23:59", "%H:%M").time(),
            is_active=True,
        )

    def _hora(self, h, m, dia=0):
        # Monday = 0 (Jun 8 2026 is a Monday)
        base = datetime(2026, 6, 8, h, m)
        actual = base + timedelta(days=dia)
        return timezone.make_aware(actual, timezone.get_current_timezone())

    def _make_lead(self, **kwargs):
        defaults = {
            "cliente": self.cliente,
            "tipo_servicio": "mudanza",
            "distrito_origen": "san isidro",
            "distrito_destino": "san miguel",
            "lista_objetos": "cama, cocina, ropero",
            "piso_origen": 3,
            "piso_destino": 2,
            "ascensor_origen": True,
            "ascensor_destino": True,
            "objetos_pesados": "",
            "modalidad_servicio": "",
        }
        defaults.update(kwargs)
        return Lead.objects.create(**defaults)

    # A. San Isidro -> San Miguel, simple, con ascensor -> puede cotizar
    @patch("apps.cotizador.services._find_similar_services")
    def test_servicio_simple_puede_cotizar(self, mock_find):
        mock_find.return_value = [(10, "fake")] * 3
        lead = self._make_lead()
        result = evaluar_mixto_inteligente(lead)
        self.assertTrue(result["puede_bot_cotizar"])
        self.assertFalse(result["requiere_asesor"])
        self.assertEqual(result["motivos"], [])

    # B. Piano -> deriva
    def test_piano_deriva_asesor(self):
        lead = self._make_lead(objetos_pesados="piano")
        result = evaluar_mixto_inteligente(lead)
        self.assertTrue(result["requiere_asesor"])
        self.assertIn("piano", str(result["motivos"]).lower())

    # C. Caja fuerte -> deriva
    def test_caja_fuerte_deriva_asesor(self):
        lead = self._make_lead(lista_objetos="cama, ropero, caja fuerte")
        result = evaluar_mixto_inteligente(lead)
        self.assertTrue(result["requiere_asesor"])
        self.assertIn("caja fuerte", str(result["motivos"]).lower())

    # D. Piso 6 sin ascensor -> deriva
    def test_piso_alto_sin_ascensor_deriva(self):
        lead = self._make_lead(piso_origen=6, ascensor_origen=False)
        result = evaluar_mixto_inteligente(lead)
        self.assertTrue(result["requiere_asesor"])
        self.assertIn("piso", str(result["motivos"]).lower())

    # E. Provincia fuera de Lima/Callao -> deriva
    def test_provincia_deriva_asesor(self):
        lead = self._make_lead(
            distrito_origen="cusco",
            distrito_destino="san miguel",
        )
        result = evaluar_mixto_inteligente(lead)
        self.assertTrue(result["requiere_asesor"])
        self.assertIn("provincia", str(result["motivos"]).lower())

    # F. Mudanza de oficina -> deriva
    def test_oficina_deriva_asesor(self):
        lead = self._make_lead(tipo_servicio="mudanza de oficina")
        result = evaluar_mixto_inteligente(lead)
        self.assertTrue(result["requiere_asesor"])
        self.assertIn("oficina", str(result["motivos"]).lower())

    # G. Embalaje full -> deriva
    def test_embalaje_full_deriva_asesor(self):
        lead = self._make_lead(modalidad_servicio="embalaje full")
        result = evaluar_mixto_inteligente(lead)
        self.assertTrue(result["requiere_asesor"])
        self.assertIn("embalaje", str(result["motivos"]).lower())

    # H. Menos de 3 históricos -> deriva en modo mixto
    @patch("apps.cotizador.services._find_similar_services")
    def test_pocos_historicos_deriva_mixto(self, mock_find):
        mock_find.return_value = []
        lead = self._make_lead()
        result = evaluar_mixto_inteligente(lead)
        self.assertTrue(result["requiere_asesor"])
        self.assertFalse(result["historicos_suficientes"])
        self.assertIn("histórico", str(result["motivos"]).lower())

    # I. Modo solo bot con pocos históricos -> mantiene fallback (should_bot_reply no evalúa históricos en modo bot)
    def test_modo_bot_pocos_historicos_mantiene_fallback(self):
        self.conf.modo_atencion = "bot"
        self.conf.save()
        # should_bot_reply solo revisa horarios en modo bot, no evalúa complejidad
        ahora = self._hora(14, 30)
        self.assertTrue(should_bot_reply(now=ahora, lead=self._make_lead()))

    # J. Override force_bot -> responde aunque esté fuera de horario
    def test_override_force_bot_fuera_horario_responde(self):
        self.conf.modo_atencion = "mixto"
        self.conf.hora_inicio_bot = "07:00"
        self.conf.hora_fin_bot = "23:00"
        self.conf.save()
        BotSchedule.objects.all().delete()
        ahora = self._hora(3, 0)  # 3 AM, no schedule
        self.assertFalse(should_bot_reply(now=ahora))
        self.conf.override_activo = True
        self.conf.override_modo = "force_bot"
        self.conf.save()
        self.assertTrue(should_bot_reply(now=ahora))

    # Lead ya derivado debe hacer que should_bot_reply retorne False
    def test_lead_ya_derivado_no_responde(self):
        lead = self._make_lead()
        lead.requiere_asesor = True
        lead.bot_pausado = True
        lead.atencion_humana = True
        lead.save()
        ahora = self._hora(14, 30)
        self.assertFalse(should_bot_reply(now=ahora, lead=lead))

    # should_bot_reply con lead simple en modo mixto -> responde
    @patch("apps.cotizador.services._find_similar_services")
    def test_lead_simple_mixto_responde(self, mock_find):
        mock_find.return_value = [(10, "fake")] * 3
        lead = self._make_lead()
        ahora = self._hora(14, 30)
        self.assertTrue(should_bot_reply(now=ahora, lead=lead))

    # should_bot_reply con lead complejo en modo mixto -> no responde + marca lead
    @patch("apps.cotizador.services._find_similar_services")
    def test_lead_complejo_mixto_deriva(self, mock_find):
        mock_find.return_value = [(10, "fake")] * 3
        lead = self._make_lead(objetos_pesados="piano")
        ahora = self._hora(14, 30)
        self.assertFalse(should_bot_reply(now=ahora, lead=lead))
        lead.refresh_from_db()
        self.assertTrue(lead.requiere_asesor)
        self.assertTrue(lead.bot_pausado)
        self.assertTrue(lead.atencion_humana)
        self.assertIsNotNone(lead.fecha_derivacion)
        self.assertIn("piano", lead.motivo_derivacion.lower())

    # Mixto respeta horarios fuera de schedule
    def test_mixto_fuera_horario_no_responde(self):
        BotSchedule.objects.all().delete()
        self.conf.hora_inicio_bot = "09:00"
        self.conf.hora_fin_bot = "18:00"
        self.conf.save()
        ahora = self._hora(20, 0)
        self.assertFalse(should_bot_reply(now=ahora))

    # K. Override force_mixto fuera de horario + caso simple -> responde
    @patch("apps.cotizador.services._find_similar_services")
    def test_override_force_mixto_fuera_horario_simple_responde(self, mock_find):
        mock_find.return_value = [(10, "fake")] * 3
        self.conf.modo_atencion = "bot"
        self.conf.hora_inicio_bot = "07:00"
        self.conf.hora_fin_bot = "23:00"
        self.conf.save()
        BotSchedule.objects.all().delete()
        ahora = self._hora(3, 0)  # 3 AM, fuera de horario
        self.assertFalse(should_bot_reply(now=ahora))
        self.conf.override_activo = True
        self.conf.override_modo = "force_mixto"
        self.conf.save()
        lead = self._make_lead()
        self.assertTrue(should_bot_reply(now=ahora, lead=lead))

    # L. Override force_mixto fuera de horario + piano -> deriva asesor
    @patch("apps.cotizador.services._find_similar_services")
    def test_override_force_mixto_fuera_horario_complejo_deriva(self, mock_find):
        mock_find.return_value = [(10, "fake")] * 3
        self.conf.modo_atencion = "bot"
        self.conf.hora_inicio_bot = "07:00"
        self.conf.hora_fin_bot = "23:00"
        self.conf.save()
        BotSchedule.objects.all().delete()
        ahora = self._hora(3, 0)  # 3 AM, fuera de horario
        self.assertFalse(should_bot_reply(now=ahora))
        self.conf.override_activo = True
        self.conf.override_modo = "force_mixto"
        self.conf.save()
        lead = self._make_lead(objetos_pesados="piano")
        self.assertFalse(should_bot_reply(now=ahora, lead=lead))
        lead.refresh_from_db()
        self.assertTrue(lead.requiere_asesor)
        self.assertIn("piano", lead.motivo_derivacion.lower())

    # M. Desactivar override force_mixto -> vuelve a respetar horario
    def test_override_force_mixto_clear_vuelve_a_horario(self):
        self.conf.modo_atencion = "bot"
        self.conf.hora_inicio_bot = "07:00"
        self.conf.hora_fin_bot = "23:00"
        self.conf.save()
        BotSchedule.objects.all().delete()
        ahora = self._hora(3, 0)  # 3 AM, fuera de horario
        self.assertFalse(should_bot_reply(now=ahora))
        self.conf.override_activo = True
        self.conf.override_modo = "force_mixto"
        self.conf.save()
        self.assertTrue(should_bot_reply(now=ahora))
        self.conf.override_activo = False
        self.conf.override_modo = "none"
        self.conf.save()
        self.assertFalse(should_bot_reply(now=ahora))

    # Mixto sin lead (nuevo cliente) -> responde para recopilar datos
    def test_mixto_sin_lead_responde(self):
        ahora = self._hora(14, 30)
        self.assertTrue(should_bot_reply(now=ahora, lead=None))


class PerChannelTests(TestCase):
    def setUp(self):
        self.channel_a = WhatsAppChannel.objects.create(
            nombre="Canal A", phone_number_id="111111", numero_visible="51911111111"
        )
        self.channel_b = WhatsAppChannel.objects.create(
            nombre="Canal B", phone_number_id="222222", numero_visible="51922222222"
        )
        self.conf_a = ConfiguracionBot.obtener(channel=self.channel_a)
        self.conf_a.modo_atencion = "bot"
        self.conf_a.bot_activo = True
        self.conf_a.hora_inicio_bot = "00:00"
        self.conf_a.hora_fin_bot = "23:59"
        self.conf_a.save()
        self.conf_b = ConfiguracionBot.obtener(channel=self.channel_b)
        self.conf_b.modo_atencion = "bot"
        self.conf_b.bot_activo = True
        self.conf_b.hora_inicio_bot = "00:00"
        self.conf_b.hora_fin_bot = "23:59"
        self.conf_b.save()
        self.cliente = Cliente.objects.create(telefono="51930000000", nombre="Test PerChannel")

    def _hora(self, h, m):
        return timezone.make_aware(
            datetime(2026, 6, 9, h, m), timezone.get_current_timezone()
        )

    def _lead(self, channel=None, **kwargs):
        defaults = {"cliente": self.cliente, "tipo_servicio": "mudanza",
                     "distrito_origen": "san isidro", "distrito_destino": "san miguel",
                     "lista_objetos": "cama", "piso_origen": 3, "piso_destino": 2,
                     "ascensor_origen": True, "ascensor_destino": True}
        defaults.update(kwargs)
        if channel:
            defaults["whatsapp_channel"] = channel
        return Lead.objects.create(**defaults)

    # Mensaje por canal A usa config A, B usa config B
    def test_canal_a_usa_config_a(self):
        ahora = self._hora(14, 0)
        self.assertTrue(should_bot_reply(now=ahora, channel=self.channel_a))
        self.assertTrue(should_bot_reply(now=ahora, channel=self.channel_b))

    # Fuera de horario: A responde, B no (B configurado con horario distinto)
    def test_canal_fuera_horario_a_responde_b_no(self):
        self.conf_b.hora_inicio_bot = "09:00"
        self.conf_b.hora_fin_bot = "18:00"
        self.conf_b.save()
        ahora = self._hora(20, 0)
        self.assertTrue(should_bot_reply(now=ahora, channel=self.channel_a))
        self.assertFalse(should_bot_reply(now=ahora, channel=self.channel_b))

    # force_mixto en A no afecta B
    def test_force_mixto_en_a_no_afecta_b(self):
        self.conf_a.hora_inicio_bot = "09:00"
        self.conf_a.hora_fin_bot = "18:00"
        self.conf_a.save()
        self.conf_b.hora_inicio_bot = "09:00"
        self.conf_b.hora_fin_bot = "18:00"
        self.conf_b.save()
        ahora = self._hora(3, 0)  # fuera de horario para ambos
        self.assertFalse(should_bot_reply(now=ahora, channel=self.channel_a))
        self.assertFalse(should_bot_reply(now=ahora, channel=self.channel_b))

        self.conf_a.override_activo = True
        self.conf_a.override_modo = "force_mixto"
        self.conf_a.save()

        self.assertTrue(should_bot_reply(now=ahora, channel=self.channel_a))
        self.assertFalse(should_bot_reply(now=ahora, channel=self.channel_b))  # B no afectado

    # Cambiar horario de A no afecta B
    def test_horario_a_no_afecta_b(self):
        self.conf_a.hora_inicio_bot = "09:00"
        self.conf_a.hora_fin_bot = "18:00"
        self.conf_a.save()
        ahora = self._hora(3, 0)
        self.assertFalse(should_bot_reply(now=ahora, channel=self.channel_a))  # A cambió a 09-18
        self.assertTrue(should_bot_reply(now=ahora, channel=self.channel_b))   # B=24h, responde

    # lead creado en A queda asociado a A
    def test_lead_asociado_a_canal(self):
        lead = self._lead(channel=self.channel_a)
        self.assertEqual(lead.whatsapp_channel_id, self.channel_a.id)

    # horarios propios por canal
    def test_horarios_por_canal(self):
        from apps.whatsapp.utils import _is_in_schedule
        BotSchedule.objects.create(channel=self.channel_a, day_of_week=0, start_time="09:00", end_time="18:00", is_active=True)
        BotSchedule.objects.create(channel=self.channel_b, day_of_week=0, start_time="14:00", end_time="22:00", is_active=True)
        ahora_10 = self._hora(10, 0)
        ahora_16 = self._hora(16, 0)
        dentro_a, _ = _is_in_schedule(self.conf_a, 0, ahora_10.time(), ahora_10, channel=self.channel_a)
        dentro_b, _ = _is_in_schedule(self.conf_b, 0, ahora_16.time(), ahora_16, channel=self.channel_b)
        self.assertTrue(dentro_a)   # 10:00 dentro de 09-18
        self.assertTrue(dentro_b)   # 16:00 dentro de 14-22
        dentro_a_16, _ = _is_in_schedule(self.conf_a, 0, ahora_16.time(), ahora_16, channel=self.channel_a)
        dentro_b_10, _ = _is_in_schedule(self.conf_b, 0, ahora_10.time(), ahora_10, channel=self.channel_b)
        self.assertTrue(dentro_a_16)  # 16:00 dentro de 09-18
        self.assertFalse(dentro_b_10)  # 10:00 fuera de 14-22


class ConversationGuardTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(telefono="51900000000", nombre="Test")

    def _lead(self, estado=Lead.NUEVO, atencion_humana=False, bot_pausado=False, requiere_asesor=False):
        return Lead.objects.create(
            cliente=self.cliente,
            estado=estado,
            atencion_humana=atencion_humana,
            bot_pausado=bot_pausado,
            requiere_asesor=requiere_asesor,
        )

    # "ya pagué por yape" -> pausa bot
    def test_pago_yape_pausa_bot(self):
        lead = self._lead()
        result = should_bot_handle_lead(lead=lead, incoming_message="ya pagué por yape")
        self.assertFalse(result["allow_bot"])
        self.assertTrue(result["pause_bot"])
        self.assertEqual(result["reason"], "posible_conversacion_humana_por_whatsapp_business")
        lead.refresh_from_db()
        self.assertTrue(lead.atencion_humana)
        self.assertTrue(lead.bot_pausado)

    # "me dijeron que venían hoy" -> pausa bot
    def test_me_dijeron_pausa_bot(self):
        lead = self._lead()
        result = should_bot_handle_lead(lead=lead, incoming_message="me dijeron que venían hoy")
        self.assertFalse(result["allow_bot"])
        self.assertEqual(result["reason"], "posible_conversacion_humana_por_whatsapp_business")

    # "quiero cambiar fecha" -> pausa bot
    def test_cambiar_fecha_pausa_bot(self):
        lead = self._lead()
        result = should_bot_handle_lead(lead=lead, incoming_message="quiero cambiar fecha")
        self.assertFalse(result["allow_bot"])
        self.assertEqual(result["reason"], "posible_conversacion_humana_por_whatsapp_business")

    # lead atencion_humana=True -> bot no responde
    def test_atencion_humana_no_responde(self):
        lead = self._lead(atencion_humana=True)
        result = should_bot_handle_lead(lead=lead, incoming_message="hola")
        self.assertFalse(result["allow_bot"])
        self.assertTrue(result["pause_bot"])
        self.assertEqual(result["reason"], "lead_en_atencion_humana")

    # lead bot_pausado=True -> bot no responde
    def test_bot_pausado_no_responde(self):
        lead = self._lead(bot_pausado=True)
        result = should_bot_handle_lead(lead=lead, incoming_message="hola")
        self.assertFalse(result["allow_bot"])
        self.assertEqual(result["reason"], "lead_en_atencion_humana")

    # lead requiere_asesor=True -> bot no responde
    def test_requiere_asesor_no_responde(self):
        lead = self._lead(requiere_asesor=True)
        result = should_bot_handle_lead(lead=lead, incoming_message="hola")
        self.assertFalse(result["allow_bot"])
        self.assertEqual(result["reason"], "lead_en_atencion_humana")

    # datos_incompletos + "del piso 2 al piso 5" -> bot continúa
    def test_datos_piso_continua(self):
        lead = self._lead(estado=Lead.DATOS_INCOMPLETOS)
        result = should_bot_handle_lead(lead=lead, incoming_message="del piso 2 al piso 5")
        self.assertTrue(result["allow_bot"])
        self.assertFalse(result["pause_bot"])

    # datos_incompletos + "con embalaje" -> bot continúa
    def test_datos_embalaje_continua(self):
        lead = self._lead(estado=Lead.DATOS_INCOMPLETOS)
        result = should_bot_handle_lead(lead=lead, incoming_message="con embalaje")
        self.assertTrue(result["allow_bot"])
        self.assertFalse(result["pause_bot"])

    # yape detectado sin acentos
    def test_yape_sin_acentos(self):
        lead = self._lead()
        result = should_bot_handle_lead(lead=lead, incoming_message="ya pague por yape")
        self.assertFalse(result["allow_bot"])

    # texto normal de cotizacion no pausa
    def test_cotizacion_normal_no_pausa(self):
        lead = self._lead()
        result = should_bot_handle_lead(lead=lead, incoming_message="cuanto cuesta una mudanza de surco a miraflores")
        self.assertTrue(result["allow_bot"])
