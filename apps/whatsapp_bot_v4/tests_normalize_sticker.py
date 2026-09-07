"""_normalize_ycloud_payload: un sticker de WhatsApp (webp) tiene que salir
como una imagen — antes la detección de tipo solo miraba image/audio/document
y el sticker caía a 'text' con contenido vacío (o se descartaba)."""
from django.test import SimpleTestCase

from apps.whatsapp_bot_v4.services.ycloud_webhook_service import _normalize_ycloud_payload


class NormalizeStickerTests(SimpleTestCase):
    def _inbound(self, msg):
        return _normalize_ycloud_payload(
            "whatsapp.inbound_message.received",
            {"id": "evt1", "timestamp": 1700000000, "whatsappInboundMessage": msg},
        )

    def test_sticker_entrante_se_normaliza_como_imagen(self):
        c = self._inbound({
            "id": "wamid1", "from": "51999888777", "type": "sticker",
            "sticker": {"id": "st_1", "mime_type": "image/webp", "link": "https://api.ycloud.com/m/st_1"},
        })
        self.assertEqual(c["type"], "image")
        self.assertEqual(c["image"]["id"], "st_1")

    def test_imagen_normal_sigue_funcionando(self):
        c = self._inbound({
            "id": "wamid2", "from": "51999888777", "type": "image",
            "image": {"id": "im_1", "link": "https://api.ycloud.com/m/im_1"},
        })
        self.assertEqual(c["type"], "image")
        self.assertEqual(c["image"]["id"], "im_1")

    def test_texto_sigue_siendo_texto(self):
        c = self._inbound({"id": "wamid3", "from": "51999888777", "type": "text", "text": {"body": "hola"}})
        self.assertEqual(c["type"], "text")
        self.assertEqual(c["text"], "hola")

    def test_sticker_saliente_echo_se_normaliza_como_imagen(self):
        c = _normalize_ycloud_payload(
            "whatsapp.smb.message.echoes",
            {
                "id": "evt2", "timestamp": 1700000000, "type": "sticker",
                "whatsappMessage": {
                    "id": "wamid4", "from": "51967619238", "to": "51999888777",
                    "type": "sticker",
                    "sticker": {"id": "st_2", "mime_type": "image/webp", "link": "https://api.ycloud.com/m/st_2"},
                },
            },
        )
        self.assertEqual(c["type"], "image")
        self.assertEqual(c["image"]["id"], "st_2")
