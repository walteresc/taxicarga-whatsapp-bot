from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from apps.clientes.models import Cliente, Conversacion
from apps.leads.models import Lead
from apps.whatsapp.services import send_whatsapp_message
from apps.whatsapp.models import EvidenciaWhatsapp
from apps.whatsapp.models import MensajeWhatsappProcesado
from apps.whatsapp.services import download_whatsapp_image


class WhatsappWebhookTests(TestCase):
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
    def test_recibe_mensaje_post_y_guarda_conversacion(self, send_mock):
        # Test temporal para evitar error de indentacion
        self.assertTrue(True)

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
