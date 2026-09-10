"""P3 · Pasarela de pago (provider fake) + órdenes de pago."""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente, ClienteUsuario
from apps.pagos import services
from apps.pagos.models import OrdenPago
from apps.servicios.cobro import aplicar_esquema
from apps.servicios.models import ConfiguracionOperaciones, Servicio

User = get_user_model()


def _servicio(precio=1000):
    cli = Cliente.objects.create(nombre="Cliente Pago", telefono="+51988000001", correo="c@x.com")
    s = Servicio.objects.create(
        cliente=cli, distrito_origen="Lima", distrito_destino="Callao",
        fecha_servicio=date.today() + timedelta(days=4), horario_servicio="09:00", precio=precio,
    )
    aplicar_esquema(s, "mitad_origen_destino")
    return s


class OrdenPagoServiceTests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()

    def test_crear_orden_toma_la_cuota_pendiente(self):
        s = _servicio(1000)
        o = services.crear_orden(s)
        self.assertEqual(o.monto, Decimal("500"))
        self.assertEqual(o.cuota, s.cuotas.order_by("orden").first())
        self.assertEqual(o.concepto, "adelanto")
        self.assertEqual(o.pasarela, "fake")

    def test_crear_orden_reutiliza_la_viva(self):
        s = _servicio(1000)
        o1 = services.crear_orden(s)
        o2 = services.crear_orden(s)
        self.assertEqual(o1.id, o2.id)

    def test_procesar_cargo_ok_genera_pago_y_salda_cuota(self):
        s = _servicio(1000)
        o = services.crear_orden(s)
        o = services.procesar_cargo(o, source_token="ok", email="pagador@x.com")
        self.assertEqual(o.estado, OrdenPago.ESTADO_PAGADA)
        self.assertIsNotNone(o.pago_generado_id)
        self.assertEqual(o.pago_generado.metodo_pago, "tarjeta")
        c1 = s.cuotas.order_by("orden").first()
        self.assertEqual(c1.estado, "pagada")

    def test_procesar_cargo_rechazado(self):
        s = _servicio(1000)
        o = services.crear_orden(s)
        o = services.procesar_cargo(o, source_token="fail")
        self.assertEqual(o.estado, OrdenPago.ESTADO_FALLIDA)
        self.assertTrue(o.detalle_error)
        self.assertEqual(s.total_pagado, Decimal("0"))

    def test_confirmar_es_idempotente(self):
        s = _servicio(1000)
        o = services.crear_orden(s)
        services.procesar_cargo(o, source_token="ok")
        services._confirmar(OrdenPago.objects.get(pk=o.pk), external_id="x")
        self.assertEqual(s.pagos.count(), 1)

    def test_webhook_confirma(self):
        s = _servicio(1000)
        o = services.crear_orden(s)
        o.external_id = "fake_chg_ABC"
        o.save(update_fields=["external_id"])
        services.confirmar_por_webhook("fake", "fake_chg_ABC", "pagada")
        o.refresh_from_db()
        self.assertEqual(o.estado, OrdenPago.ESTADO_PAGADA)

    def test_expirar_vencidas(self):
        from django.utils import timezone
        s = _servicio(1000)
        o = services.crear_orden(s)
        OrdenPago.objects.filter(pk=o.pk).update(expira_en=timezone.now() - timedelta(days=1))
        self.assertFalse(OrdenPago.objects.get(pk=o.pk).pagable)
        services.expirar_vencidas()
        self.assertEqual(OrdenPago.objects.get(pk=o.pk).estado, OrdenPago.ESTADO_EXPIRADA)


class PublicCheckoutAPITests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()
        self.s = _servicio(1200)
        self.o = services.crear_orden(self.s)

    def test_get_orden_publica(self):
        r = self.client.get(f"/api/v2/pay/{self.o.token}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["amount"], 600.0)
        self.assertEqual(r.data["gateway"]["provider"], "fake")
        self.assertNotIn("commission", r.data)

    def test_charge_ok(self):
        r = self.client.post(f"/api/v2/pay/{self.o.token}/charge",
                             {"sourceToken": "ok", "email": "x@y.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["state"], "pagada")
        self.assertEqual(self.s.total_pagado, Decimal("600"))

    def test_charge_rechazado(self):
        r = self.client.post(f"/api/v2/pay/{self.o.token}/charge", {"sourceToken": "fail"}, format="json")
        self.assertEqual(r.data["state"], "fallida")

    def test_webhook_endpoint(self):
        self.o.external_id = "fake_chg_X"
        self.o.save(update_fields=["external_id"])
        r = self.client.post("/api/v2/payments/webhook/fake",
                             data=json.dumps({"external_id": "fake_chg_X", "status": "succeeded"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.o.refresh_from_db()
        self.assertEqual(self.o.estado, OrdenPago.ESTADO_PAGADA)


class PaymentLinkAPITests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()
        Group.objects.get_or_create(name="Asesor de Ventas")
        self.u = User.objects.create_user("pl_ase", password="x")
        self.u.groups.add(Group.objects.get(name="Asesor de Ventas"))
        self.s = _servicio(1000)

    def test_asesor_genera_link(self):
        self.client.force_authenticate(self.u)
        r = self.client.post(f"/api/v2/pipeline/bookings/{self.s.id}/payment-link", {}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["url"].startswith("/pagar/"))
        self.assertEqual(r.data["amount"], 500.0)

    def test_anonimo_no_puede(self):
        r = self.client.post(f"/api/v2/pipeline/bookings/{self.s.id}/payment-link", {}, format="json")
        self.assertEqual(r.status_code, 403)


class CustomerPortalPayTests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()
        Group.objects.get_or_create(name="Cliente Portal")
        self.s = _servicio(1000)
        # el portal usa Lead; enlazamos uno
        from apps.leads.models import Lead
        self.lead = Lead.objects.create(cliente=self.s.cliente, tipo_servicio="carga", codigo="CRG-PAY1")
        self.s.lead_origen = self.lead
        self.s.save(update_fields=["lead_origen"])
        self.user = User.objects.create_user("pay_cust", password="x")
        self.user.groups.add(Group.objects.get(name="Cliente Portal"))
        ClienteUsuario.objects.create(usuario=self.user, cliente=self.s.cliente)

    def test_cliente_genera_orden(self):
        self.client.force_authenticate(self.user)
        r = self.client.post("/api/v2/portal/customer/loads/CRG-PAY1/pay", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["url"].startswith("/pagar/"))
        self.assertEqual(OrdenPago.objects.filter(servicio=self.s, origen="portal").count(), 1)

    def test_detalle_incluye_billing(self):
        self.client.force_authenticate(self.user)
        r = self.client.get("/api/v2/portal/customer/loads/CRG-PAY1")
        self.assertIn("billing", r.data)
        self.assertEqual(len(r.data["billing"]["installments"]), 2)
