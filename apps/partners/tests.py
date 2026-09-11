"""P4 · API de socios: llaves, cotizar/crear envío, idempotencia, webhooks."""
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.encomiendas.models import Envio, ZonaReparto
from apps.partners.models import ApiKey, IdempotencyRecord, SocioComercial, WebhookDelivery
from apps.partners.services import con_idempotencia, firmar, notificar

User = get_user_model()


def _seed():
    if not ZonaReparto.objects.exists():
        call_command("seed_encomiendas")


class ApiKeyTests(APITestCase):
    def test_generar_y_resolver(self):
        socio = SocioComercial.objects.create(nombre="Tienda X")
        key, token = ApiKey.generar(socio, entorno=ApiKey.ENTORNO_TEST)
        self.assertTrue(token.startswith(key.prefix + "."))
        resuelto = ApiKey.resolver(token)
        self.assertEqual(resuelto.id, key.id)

    def test_token_invalido(self):
        self.assertIsNone(ApiKey.resolver("basura"))
        self.assertIsNone(ApiKey.resolver("pk_test_x.secreto_incorrecto"))

    def test_socio_inactivo_no_resuelve(self):
        socio = SocioComercial.objects.create(nombre="Y", activo=False)
        _, token = ApiKey.generar(socio)
        self.assertIsNone(ApiKey.resolver(token))

    def test_key_revocada_no_resuelve(self):
        socio = SocioComercial.objects.create(nombre="Z")
        key, token = ApiKey.generar(socio)
        key.activa = False
        key.save()
        self.assertIsNone(ApiKey.resolver(token))


class PartnerApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        _seed()

    def setUp(self):
        self.socio = SocioComercial.objects.create(nombre="Tienda API")
        _, self.token = ApiKey.generar(self.socio, entorno=ApiKey.ENTORNO_TEST)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_sin_llave_403_o_401(self):
        r = self.client.get("/api/partners/v1/coverage")
        self.assertIn(r.status_code, (401, 403))

    def test_coverage_y_quote(self):
        r = self.client.get("/api/partners/v1/coverage", **self.auth)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(len(r.data["zones"]) > 0)

        r = self.client.post("/api/partners/v1/quotes",
                             {"originDistrict": "Miraflores", "destDistrict": "Miraflores", "weightKg": 2},
                             format="json", **self.auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["price"], 12.0)

    def test_crear_envio_y_consultar(self):
        r = self.client.post("/api/partners/v1/shipments", {
            "senderName": "Tienda API", "originDistrict": "Miraflores", "originAddress": "Av. Larco 1",
            "recipientName": "Cliente Final", "destDistrict": "Surco", "destAddress": "Av. Caminos 2",
            "weightKg": 2, "externalRef": "order-99",
        }, format="json", **self.auth)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["externalRef"], "order-99")
        self.assertEqual(r.data["state"], "registered")
        code = r.data["id"]

        envio = Envio.objects.get(codigo=code)
        self.assertEqual(envio.socio_id, self.socio.id)

        r = self.client.get(f"/api/partners/v1/shipments/{code}", **self.auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["id"], code)

        # otro socio no puede verlo
        otro = SocioComercial.objects.create(nombre="Otra tienda")
        _, tok2 = ApiKey.generar(otro)
        r = self.client.get(f"/api/partners/v1/shipments/{code}", HTTP_AUTHORIZATION=f"Bearer {tok2}")
        self.assertEqual(r.status_code, 404)

    def test_idempotencia_no_duplica(self):
        body = {
            "senderName": "T", "originDistrict": "Ate", "originAddress": "Calle 1",
            "recipientName": "C", "destDistrict": "Ate", "destAddress": "Calle 2", "weightKg": 1,
        }
        headers = dict(self.auth, HTTP_IDEMPOTENCY_KEY="req-abc")
        r1 = self.client.post("/api/partners/v1/shipments", body, format="json", **headers)
        r2 = self.client.post("/api/partners/v1/shipments", body, format="json", **headers)
        self.assertEqual(r1.data["id"], r2.data["id"])
        self.assertEqual(Envio.objects.filter(socio=self.socio).count(), 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)

    def test_cancelar_envio(self):
        r = self.client.post("/api/partners/v1/shipments", {
            "senderName": "T", "originDistrict": "Ate", "originAddress": "Calle 1",
            "recipientName": "C", "destDistrict": "Ate", "destAddress": "Calle 2", "weightKg": 1,
        }, format="json", **self.auth)
        code = r.data["id"]
        r = self.client.post(f"/api/partners/v1/shipments/{code}/cancel", {}, format="json", **self.auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["state"], "cancelled")

    @patch("apps.partners.services.requests.post")
    def test_webhook_se_dispara_al_asignar(self, post_mock):
        from apps.catalogo.models import TipoVehiculo
        from apps.tercerizacion.models import Transportista

        post_mock.return_value = Mock(status_code=200)
        self.socio.webhook_url = "https://tienda.example.com/webhooks/limaexpress"
        self.socio.webhook_secret = "shh"
        self.socio.save()

        r = self.client.post("/api/partners/v1/shipments", {
            "senderName": "T", "originDistrict": "Ate", "originAddress": "Calle 1",
            "recipientName": "C", "destDistrict": "Ate", "destAddress": "Calle 2", "weightKg": 1,
        }, format="json", **self.auth)
        code = r.data["id"]
        self.assertTrue(post_mock.called)  # shipment.created

        carrier = Transportista.objects.create(nombre="M1")
        from apps.encomiendas import services as enc
        envio = Envio.objects.get(codigo=code)
        post_mock.reset_mock()
        enc.asignar_envio(envio, carrier)
        self.assertTrue(post_mock.called)
        sent_body = post_mock.call_args.kwargs["data"]
        self.assertIn(b"shipment.assigned", sent_body)
        self.assertEqual(WebhookDelivery.objects.filter(socio=self.socio).count(), 2)


class WebhookServiceTests(APITestCase):
    def test_firma_hmac(self):
        f1 = firmar("secreto", b"hola")
        f2 = firmar("secreto", b"hola")
        f3 = firmar("otro", b"hola")
        self.assertEqual(f1, f2)
        self.assertNotEqual(f1, f3)

    def test_sin_webhook_url_queda_fallido(self):
        socio = SocioComercial.objects.create(nombre="Sin webhook")
        entrega = notificar(socio, "shipment.created", {"id": "X"})
        self.assertEqual(entrega.estado, WebhookDelivery.ESTADO_FALLIDO)

    def test_idempotencia_reutiliza_respuesta(self):
        socio = SocioComercial.objects.create(nombre="Idem")
        calls = []

        def fn():
            calls.append(1)
            return 201, {"ok": True}

        s1, b1, replay1 = con_idempotencia(socio, "k1", "POST /x", fn)
        s2, b2, replay2 = con_idempotencia(socio, "k1", "POST /x", fn)
        self.assertEqual((s1, b1), (s2, b2))
        self.assertFalse(replay1)
        self.assertTrue(replay2)
        self.assertEqual(len(calls), 1)


class PartnerAdminApiTests(APITestCase):
    def setUp(self):
        Group.objects.get_or_create(name="Administrador")
        self.admin = User.objects.create_user("partner_admin", password="x")
        self.admin.groups.add(Group.objects.get(name="Administrador"))
        self.client.force_authenticate(self.admin)

    def test_crear_socio_y_generar_llave(self):
        r = self.client.post("/api/v2/partners/", {"name": "Tienda Nueva", "webhookUrl": "https://x.com/wh"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        pid = r.data["id"]
        r = self.client.post(f"/api/v2/partners/{pid}/keys", {"environment": "test"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertIn("token", r.data)
        key_id = r.data["id"]
        r = self.client.get(f"/api/v2/partners/{pid}/")
        self.assertEqual(len(r.data["keys"]), 1)
        self.assertNotIn("token", r.data["keys"][0])  # no se repite el secreto
        r = self.client.post(f"/api/v2/partners/{pid}/keys/{key_id}/revoke", {}, format="json")
        self.assertEqual(r.status_code, 200)
