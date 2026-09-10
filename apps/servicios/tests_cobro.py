"""P2 · Plan de cobro por cuotas."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente
from apps.servicios.cobro import aplicar_esquema, estado_cobro, recalcular_cuotas
from apps.servicios.models import ConfiguracionOperaciones, CuotaServicio, Servicio
from apps.servicios.services import registrar_pago

User = get_user_model()


def _servicio(precio=1000):
    cli = Cliente.objects.create(nombre="C", telefono="+51922000001")
    return Servicio.objects.create(
        cliente=cli, distrito_origen="Lima", distrito_destino="Callao",
        fecha_servicio=date.today() + timedelta(days=5), horario_servicio="09:00", precio=precio,
    )


class EsquemaTests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()

    def test_preset_50_50(self):
        s = _servicio(1000)
        cuotas = aplicar_esquema(s, "mitad_origen_destino")
        self.assertEqual(len(cuotas), 2)
        self.assertEqual([c.monto for c in cuotas], [Decimal("500"), Decimal("500")])
        self.assertEqual([c.disparador for c in cuotas], ["origen", "destino"])

    def test_preset_adelanto_saldo_usa_config(self):
        cfg = ConfiguracionOperaciones.get_solo()
        cfg.adelanto_pct_default = 40
        cfg.save()
        s = _servicio(1000)
        cuotas = aplicar_esquema(s, "adelanto_saldo")
        self.assertEqual(cuotas[0].monto, Decimal("400"))
        self.assertEqual(cuotas[1].monto, Decimal("600"))

    def test_credito_30_calcula_vencimiento(self):
        s = _servicio(2000)
        c = aplicar_esquema(s, "credito_30")[0]
        self.assertEqual(c.fecha_vencimiento, s.fecha_servicio + timedelta(days=30))
        self.assertEqual(c.monto, Decimal("2000"))

    def test_cuotas_a_medida(self):
        s = _servicio(1000)
        cuotas = aplicar_esquema(s, cuotas=[
            {"trigger": "reserva", "base": "monto", "value": 300},
            {"trigger": "destino", "base": "monto", "value": 700},
        ])
        self.assertEqual([c.monto for c in cuotas], [Decimal("300"), Decimal("700")])

    def test_porcentajes_deben_sumar_100(self):
        s = _servicio(1000)
        with self.assertRaises(ValidationError):
            aplicar_esquema(s, cuotas=[
                {"trigger": "reserva", "base": "porcentaje", "value": 30},
                {"trigger": "destino", "base": "porcentaje", "value": 50},
            ])

    def test_recalcular_al_cambiar_precio(self):
        s = _servicio(1000)
        aplicar_esquema(s, "mitad_origen_destino")
        s.precio = 2000
        s.save()
        recalcular_cuotas(s)
        self.assertEqual([c.monto for c in s.cuotas.order_by("orden")], [Decimal("1000"), Decimal("1000")])


class PagoAsignacionTests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()
        self.s = _servicio(1000)
        aplicar_esquema(self.s, "mitad_origen_destino")

    def test_pago_salda_cuota_mas_antigua(self):
        registrar_pago(self.s, concepto="adelanto", metodo_pago="yape", monto=500)
        c1, c2 = self.s.cuotas.order_by("orden")
        self.assertEqual(c1.estado, "pagada")
        self.assertEqual(c2.estado, "pendiente")

    def test_pago_parcial(self):
        registrar_pago(self.s, concepto="adelanto", metodo_pago="yape", monto=200)
        c1 = self.s.cuotas.order_by("orden").first()
        self.assertEqual(c1.estado, "parcial")
        self.assertEqual(c1.pagado, Decimal("200"))

    def test_pago_a_cuota_especifica(self):
        c2 = self.s.cuotas.order_by("orden").last()
        registrar_pago(self.s, concepto="parcial", metodo_pago="plin", monto=500, cuota_id=c2.id)
        self.assertEqual(c2.estado, "pagada")

    def test_estado_cobro_shape(self):
        registrar_pago(self.s, concepto="adelanto", metodo_pago="yape", monto=500)
        e = estado_cobro(self.s)
        self.assertEqual(e["total"], 1000.0)
        self.assertEqual(e["paid"], 500.0)
        self.assertEqual(e["balance"], 500.0)
        self.assertEqual(len(e["installments"]), 2)


class BillingAPITests(APITestCase):
    def setUp(self):
        ConfiguracionOperaciones.objects.filter(pk=1).delete()
        for g in ("Administrador",):
            Group.objects.get_or_create(name=g)
        self.u = User.objects.create_user("cobro_admin", password="x", is_staff=True)
        self.u.groups.add(Group.objects.get(name="Administrador"))
        self.client.force_authenticate(self.u)
        self.s = _servicio(1200)

    def test_presets(self):
        r = self.client.get("/api/v2/billing/presets")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(p["key"] == "credito_30" for p in r.data["presets"]))

    def test_put_billing_y_get(self):
        r = self.client.put(f"/api/v2/pipeline/bookings/{self.s.id}/billing",
                            {"scheme": "mitad_origen_destino"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(r.data["installments"]), 2)
        r = self.client.get(f"/api/v2/pipeline/bookings/{self.s.id}/billing")
        self.assertEqual(r.data["installments"][0]["amount"], 600.0)

    def test_settings(self):
        r = self.client.patch("/api/v2/billing/settings",
                              {"defaultScheme": "total_destino", "defaultAdvancePercent": 25}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["defaultScheme"], "total_destino")
        cfg = ConfiguracionOperaciones.get_solo()
        self.assertEqual(cfg.adelanto_pct_default, Decimal("25"))
