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
        self.assertEqual(r["precio_min"], Decimal("50"))  # 10 kg * 5 = 50 > mínimo 35
        self.assertEqual(r["precio_max"], Decimal("50"))  # sin _max cargado, el rango colapsa a un solo valor
        self.assertEqual(r["dias_estimados"], 4)

    def test_aplica_minimo(self):
        _tarifas_base()
        r = resolver_tarifa_parcial("arequipa", 2)  # 2 kg * 5 = 10 < mínimo 35
        self.assertEqual(r["precio_min"], Decimal("35"))
        self.assertEqual(r["precio_max"], Decimal("35"))

    def test_tramo_de_peso_alto_sin_tope(self):
        _tarifas_base()
        r = resolver_tarifa_parcial("arequipa", 100)  # 100 kg * 3 = 300
        self.assertEqual(r["precio_min"], Decimal("300"))
        self.assertEqual(r["dias_estimados"], 5)

    def test_destino_sin_tabla_propia_cae_al_general(self):
        _tarifas_base()
        r = resolver_tarifa_parcial("trujillo", 10)
        self.assertEqual(r["precio_min"], Decimal("60"))  # 10 kg * 6 = 60 (tramo general)
        self.assertEqual(r["dias_estimados"], 6)

    def test_modalidad_completa_no_ve_tramos_de_parcial(self):
        _tarifas_base()  # todos default modalidad="parcial"
        self.assertIsNone(resolver_tarifa_parcial("arequipa", 10, modalidad=Lead.MODO_CARGA_COMPLETA))

    def test_volumen_mas_caro_que_peso_gana(self):
        TarifaCargaParcial.objects.create(
            destino="ica", peso_desde_kg=0, peso_hasta_kg=None,
            precio_por_kg=Decimal("3"), precio_por_m3=Decimal("100"), monto_minimo=Decimal("30"),
        )
        r = resolver_tarifa_parcial("ica", 10, volumen_m3=2)  # 10*3=30 vs 2*100=200
        self.assertEqual(r["precio_min"], Decimal("200"))

    def test_sin_precio_por_m3_configurado_ignora_volumen(self):
        _tarifas_base()  # ninguna tiene precio_por_m3
        r = resolver_tarifa_parcial("arequipa", 10, volumen_m3=50)
        self.assertEqual(r["precio_min"], Decimal("50"))  # igual que sin volumen

    def test_con_precio_kg_max_devuelve_rango(self):
        TarifaCargaParcial.objects.create(
            destino="ica", peso_desde_kg=0, peso_hasta_kg=None,
            precio_por_kg=Decimal("3"), precio_por_kg_max=Decimal("4"), monto_minimo=Decimal("10"),
        )
        r = resolver_tarifa_parcial("ica", 10)  # 10*3=30 (min) .. 10*4=40 (max)
        self.assertEqual(r["precio_min"], Decimal("30"))
        self.assertEqual(r["precio_max"], Decimal("40"))

    def test_precio_kg_max_no_puede_quedar_bajo_el_minimo(self):
        # Si el mínimo se dispara por el monto_minimo (piso), el máximo debe
        # seguirlo hacia arriba, nunca mostrar max < min.
        TarifaCargaParcial.objects.create(
            destino="ica", peso_desde_kg=0, peso_hasta_kg=None,
            precio_por_kg=Decimal("3"), precio_por_kg_max=Decimal("4"), monto_minimo=Decimal("50"),
        )
        r = resolver_tarifa_parcial("ica", 10)  # 10*3=30 y 10*4=40, ambos bajo el piso de 50
        self.assertEqual(r["precio_min"], Decimal("50"))
        self.assertEqual(r["precio_max"], Decimal("50"))


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

    def test_modo_completa_no_usa_tarifas_de_modalidad_parcial(self):
        # La tabla ahora cubre las dos modalidades (campo `modalidad`), pero
        # son tablas independientes: _tarifas_base() solo cargó tramos
        # "parcial" (el default del modelo) — un lead completo/exclusivo no
        # debe usarlos, así que cae a asesor igual que si no hubiera tabla.
        lead = Lead.objects.create(
            cliente=self.cliente, es_interprovincial=True, modo_carga=Lead.MODO_CARGA_COMPLETA,
            distrito_origen="Lima", distrito_destino="Arequipa", peso_carga_kg=Decimal("20"),
        )
        cot = cotizar_lead(lead)
        self.assertEqual(cot.modo, Cotizacion.MODO_MANUAL)
        self.assertIsNone(cot.dias_estimados)

    def test_modo_completa_con_tarifa_propia_cotiza_automatico(self):
        TarifaCargaParcial.objects.create(
            destino="arequipa", modalidad=Lead.MODO_CARGA_COMPLETA,
            peso_desde_kg=0, peso_hasta_kg=None,
            precio_por_kg=Decimal("8"), monto_minimo=Decimal("100"), dias_estimados=3,
        )
        lead = Lead.objects.create(
            cliente=self.cliente, es_interprovincial=True, modo_carga=Lead.MODO_CARGA_COMPLETA,
            distrito_origen="Lima", distrito_destino="Arequipa", peso_carga_kg=Decimal("20"),
        )
        cot = cotizar_lead(lead)
        self.assertEqual(cot.modo, Cotizacion.MODO_AUTOMATICO)
        self.assertEqual(cot.precio_recomendado, Decimal("160"))  # 20 kg * 8
        self.assertEqual(cot.dias_estimados, 3)

    def test_peso_volumetrico_cobra_el_mayor_entre_peso_y_volumen(self):
        TarifaCargaParcial.objects.create(
            destino="ica", modalidad=Lead.MODO_CARGA_PARCIAL,
            peso_desde_kg=0, peso_hasta_kg=None,
            precio_por_kg=Decimal("3"), precio_por_m3=Decimal("100"), monto_minimo=Decimal("30"), dias_estimados=2,
        )
        # Carga liviana pero grande: 10kg * 3 = 30, pero 2m3 * 100 = 200 — debe cobrar 200.
        lead = self._lead(distrito_destino="Ica", peso_carga_kg=Decimal("10"), volumen_carga_m3=Decimal("2"))
        cot = cotizar_lead(lead)
        self.assertEqual(cot.modo, Cotizacion.MODO_AUTOMATICO)
        self.assertEqual(cot.precio_recomendado, Decimal("200"))


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

    def test_crud_con_modalidad_y_precio_por_m3(self):
        self.client.force_authenticate(self.gerente)
        r = self.client.post("/api/v2/outsourcing/partial-tariffs", {
            "destination": "cusco", "modality": "completa", "weightFrom": 0, "weightTo": None,
            "pricePerKg": 8, "pricePerM3": 150, "minAmount": 100, "daysEstimated": 3,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["modality"], "completa")
        self.assertEqual(r.data["pricePerM3"], 150.0)
        # default: sin mandar modality, queda "parcial" (comportamiento previo intacto).
        r2 = self.client.post("/api/v2/outsourcing/partial-tariffs", {
            "destination": "puno", "weightFrom": 0, "pricePerKg": 5,
        }, format="json")
        self.assertEqual(r2.data["modality"], "parcial")
        self.assertIsNone(r2.data["pricePerM3"])

    def test_rechaza_modalidad_invalida(self):
        self.client.force_authenticate(self.gerente)
        r = self.client.post("/api/v2/outsourcing/partial-tariffs", {
            "destination": "cusco", "modality": "express", "weightFrom": 0, "pricePerKg": 5,
        }, format="json")
        self.assertEqual(r.status_code, 400)

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
