"""Carga nacional PARCIAL/consolidada (LTL) — Fase 2, 2026-09.

Tabla de tarifas por destino × peso (`TarifaCargaParcial`), el resolver de
`apps.tercerizacion.services`, la API de administración y el enganche con
`cotizar_lead` cuando `Lead.modo_carga == "parcial"`.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from apps.clientes.models import Cliente
from apps.cotizador.models import Cotizacion
from apps.cotizador.services import cotizar_lead
from apps.leads.models import Lead
from apps.tercerizacion.models import TarifaCargaParcial
from apps.tercerizacion.services import resolver_tarifa_parcial

User = get_user_model()


def _tarifas_base():
    TarifaCargaParcial.objects.bulk_create([
        TarifaCargaParcial(destino="", peso_desde_kg=0, peso_hasta_kg=50,
                            precio_por_kg=Decimal("6"), monto_minimo=Decimal("40"), dias_estimados=6),
        TarifaCargaParcial(destino="", peso_desde_kg=50, peso_hasta_kg=None,
                            precio_por_kg=Decimal("4"), monto_minimo=Decimal("40"), dias_estimados=7),
        TarifaCargaParcial(destino="arequipa", peso_desde_kg=0, peso_hasta_kg=50,
                            precio_por_kg=Decimal("5"), monto_minimo=Decimal("35"), dias_estimados=4),
        TarifaCargaParcial(destino="arequipa", peso_desde_kg=50, peso_hasta_kg=None,
                            precio_por_kg=Decimal("3"), monto_minimo=Decimal("35"), dias_estimados=5),
    ])


class ResolverTarifaParcialTests(APITestCase):
    def setUp(self):
        TarifaCargaParcial.objects.all().delete()

    def test_sin_tabla_devuelve_none(self):
        self.assertIsNone(resolver_tarifa_parcial("arequipa", 10))

    def test_sin_peso_devuelve_none(self):
        _tarifas_base()
        self.assertIsNone(resolver_tarifa_parcial("arequipa", None))
        self.assertIsNone(resolver_tarifa_parcial("arequipa", 0))

    def test_destino_con_tabla_propia(self):
        _tarifas_base()
        r = resolver_tarifa_parcial("Arequipa", 10)  # case-insensitive
        self.assertEqual(r["precio"], Decimal("50"))  # 10 kg * 5 = 50 > mínimo 35
        self.assertEqual(r["dias_estimados"], 4)

    def test_aplica_minimo(self):
        _tarifas_base()
        r = resolver_tarifa_parcial("arequipa", 2)  # 2 kg * 5 = 10 < mínimo 35
        self.assertEqual(r["precio"], Decimal("35"))

    def test_tramo_de_peso_alto_sin_tope(self):
        _tarifas_base()
        r = resolver_tarifa_parcial("arequipa", 100)  # 100 kg * 3 = 300
        self.assertEqual(r["precio"], Decimal("300"))
        self.assertEqual(r["dias_estimados"], 5)

    def test_destino_sin_tabla_propia_cae_al_general(self):
        _tarifas_base()
        r = resolver_tarifa_parcial("trujillo", 10)
        self.assertEqual(r["precio"], Decimal("60"))  # 10 kg * 6 = 60 (tramo general)
        self.assertEqual(r["dias_estimados"], 6)


class CotizarCargaParcialTests(APITestCase):
    def setUp(self):
        TarifaCargaParcial.objects.all().delete()
        _tarifas_base()
        self.cliente = Cliente.objects.create(telefono="+51900222333", nombre="Parcial Test")

    def _lead(self, **kwargs):
        return Lead.objects.create(
            cliente=self.cliente, es_interprovincial=True, modo_carga=Lead.MODO_CARGA_PARCIAL,
            distrito_origen="Lima", **kwargs,
        )

    def test_con_tarifa_cotiza_automatico(self):
        lead = self._lead(distrito_destino="Arequipa", peso_carga_kg=Decimal("20"))
        cot = cotizar_lead(lead)
        self.assertEqual(cot.modo, Cotizacion.MODO_AUTOMATICO)
        self.assertEqual(cot.precio_recomendado, Decimal("100"))  # 20 kg * 5
        self.assertEqual(cot.dias_estimados, 4)

    def test_sin_tarifa_para_destino_ni_general_deriva_a_asesor(self):
        TarifaCargaParcial.objects.filter(destino="").delete()
        lead = self._lead(distrito_destino="Iquitos", peso_carga_kg=Decimal("20"))
        cot = cotizar_lead(lead)
        self.assertEqual(cot.modo, Cotizacion.MODO_MANUAL)

    def test_sin_peso_deriva_a_asesor(self):
        lead = self._lead(distrito_destino="Arequipa", peso_carga_kg=None)
        cot = cotizar_lead(lead)
        self.assertEqual(cot.modo, Cotizacion.MODO_MANUAL)

    def test_modo_completa_no_usa_la_tabla_parcial(self):
        # Misma carga pero modo completa: sigue el camino de siempre (motor de
        # históricos / fallback), no la tabla de carga parcial.
        lead = Lead.objects.create(
            cliente=self.cliente, es_interprovincial=True, modo_carga=Lead.MODO_CARGA_COMPLETA,
            distrito_origen="Lima", distrito_destino="Arequipa", peso_carga_kg=Decimal("20"),
        )
        cot = cotizar_lead(lead)
        self.assertIsNone(cot.dias_estimados)


class PartialTariffsAPITests(APITestCase):
    def setUp(self):
        TarifaCargaParcial.objects.all().delete()
        for g in ("Gerencia", "Despacho"):
            Group.objects.get_or_create(name=g)
        self.gerente = User.objects.create_user("pt_ger", password="x")
        self.gerente.groups.add(Group.objects.get(name="Gerencia"))
        self.despacho = User.objects.create_user("pt_desp", password="x")
        self.despacho.groups.add(Group.objects.get(name="Despacho"))

    def test_despacho_no_puede(self):
        self.client.force_authenticate(self.despacho)
        self.assertEqual(self.client.get("/api/v2/outsourcing/partial-tariffs").status_code, 403)

    def test_crud(self):
        self.client.force_authenticate(self.gerente)
        r = self.client.post("/api/v2/outsourcing/partial-tariffs", {
            "destination": "cusco", "weightFrom": 0, "weightTo": 50,
            "pricePerKg": 5.5, "minAmount": 40, "daysEstimated": 5,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        tid = r.data["id"]
        r = self.client.patch(f"/api/v2/outsourcing/partial-tariffs/{tid}", {"pricePerKg": 6}, format="json")
        self.assertEqual(r.data["pricePerKg"], 6.0)
        r = self.client.get("/api/v2/outsourcing/partial-tariffs")
        self.assertEqual(len(r.data["tariffs"]), 1)
        self.assertEqual(self.client.delete(f"/api/v2/outsourcing/partial-tariffs/{tid}").status_code, 204)

    def test_rechaza_rango_de_peso_invalido(self):
        self.client.force_authenticate(self.gerente)
        r = self.client.post("/api/v2/outsourcing/partial-tariffs", {
            "destination": "", "weightFrom": 100, "weightTo": 10, "pricePerKg": 5,
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_rechaza_precio_no_positivo(self):
        self.client.force_authenticate(self.gerente)
        r = self.client.post("/api/v2/outsourcing/partial-tariffs", {
            "destination": "", "weightFrom": 0, "pricePerKg": 0,
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_seed_idempotente(self):
        from django.core.management import call_command
        call_command("seed_tarifas_parciales")
        n = TarifaCargaParcial.objects.count()
        self.assertGreater(n, 0)
        call_command("seed_tarifas_parciales")
        self.assertEqual(TarifaCargaParcial.objects.count(), n)
