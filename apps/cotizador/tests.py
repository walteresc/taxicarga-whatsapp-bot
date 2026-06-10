from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.cotizador.models import Cotizacion, ServicioHistorico
from apps.cotizador.services import cotizar_lead, crear_servicio_historico_desde_lead
from apps.leads.models import Lead


class ImportarHistoricosTests(TestCase):
    def test_importa_csv_de_ejemplo(self):
        call_command("importar_historicos")

        self.assertEqual(ServicioHistorico.objects.count(), 10)

    def test_importa_wally_sin_datos_personales(self):
        call_command(
            "importar_wally_sql",
            "apps/cotizador/tests_data/wally_sample.sql",
        )

        self.assertEqual(ServicioHistorico.objects.count(), 2)
        reserved = ServicioHistorico.objects.get(referencia_externa="100")
        self.assertEqual(reserved.fuente, "wally")
        self.assertTrue(reserved.cerrado)
        self.assertEqual(reserved.piso_origen, 2)
        self.assertTrue(reserved.ascensor_origen)
        self.assertFalse(reserved.ascensor_destino)
        self.assertEqual(
            reserved.modalidad_servicio,
            "embalaje basico y traslado",
        )
        self.assertTrue(reserved.requiere_desarmado)
        self.assertIn("desarmado", reserved.observaciones)
        self.assertIn("armado", reserved.observaciones)
        self.assertNotIn("example.com", reserved.observaciones)
        self.assertNotIn("example.com", reserved.lista_objetos)


class CotizadorTests(TestCase):
    def test_cotiza_con_historicos_similares(self):
        cliente = Cliente.objects.create(telefono="51911111111")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Miraflores",
            distrito_destino="Surco",
            piso_origen=2,
            piso_destino=1,
            ascensor_origen=True,
            ascensor_destino=True,
            lista_objetos="cama queen refrigeradora sofa mesa cajas",
        )
        for price in ["400.00", "450.00", "500.00"]:
            ServicioHistorico.objects.create(
                fecha="2026-01-01",
                tipo_servicio="mudanza",
                distrito_origen="Miraflores",
                distrito_destino="Surco",
                piso_origen=2,
                piso_destino=1,
                ascensor_origen=True,
                ascensor_destino=True,
                lista_objetos="cama queen refrigeradora sofa mesa cajas",
                precio_cotizado=Decimal(price),
                precio_final=Decimal(price),
                cerrado=True,
            )

        cotizacion = cotizar_lead(lead)

        self.assertEqual(cotizacion.servicios_similares_encontrados, 3)
        self.assertEqual(cotizacion.precio_min, Decimal("420.00"))
        self.assertEqual(cotizacion.precio_max, Decimal("480.00"))
        self.assertEqual(cotizacion.precio_recomendado, Decimal("450.00"))

    def test_cotiza_con_reglas_si_no_hay_historicos(self):
        cliente = Cliente.objects.create(telefono="51922222222")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="carga",
            distrito_origen="Barranco",
            distrito_destino="Lince",
            lista_objetos="mesa y cuatro cajas",
        )

        cotizacion = cotizar_lead(lead)

        self.assertEqual(cotizacion.servicios_similares_encontrados, 0)
        self.assertGreater(cotizacion.precio_recomendado, Decimal("0.00"))
        self.assertEqual(Cotizacion.objects.count(), 1)

    def test_factores_operativos_incrementan_precio(self):
        cliente = Cliente.objects.create(telefono="51922222223")
        simple = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Surco",
            lista_objetos="cama y cajas",
            modalidad_servicio="solo traslado",
        )
        complex_lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Surco",
            lista_objetos="cama, refrigeradora, ropero y cajas",
            objetos_pesados="refrigeradora de 2 puertas, ropero",
            modalidad_servicio="embalaje completo y traslado",
            requiere_desarmado=True,
            distancia_carga_origen_m=80,
            distancia_carga_destino_m=60,
        )

        simple_quote = cotizar_lead(simple)
        complex_quote = cotizar_lead(complex_lead)

        self.assertGreater(
            complex_quote.precio_recomendado,
            simple_quote.precio_recomendado,
        )

    def test_mediana_evital_que_un_atipico_domine_la_cotizacion(self):
        cliente = Cliente.objects.create(telefono="51922222224")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="La Molina",
            lista_objetos="cama, refrigeradora y cajas",
        )
        for price in ["350.00", "400.00", "450.00", "5000.00"]:
            ServicioHistorico.objects.create(
                fecha="2026-01-01",
                tipo_servicio="mudanza",
                distrito_origen="Santiago de Surco",
                distrito_destino="La Molina",
                lista_objetos="cama, refrigeradora y cajas",
                precio_cotizado=Decimal(price),
                precio_final=Decimal(price),
                cerrado=True,
            )

        quote = cotizar_lead(lead)

        self.assertEqual(quote.precio_recomendado, Decimal("400.00"))
        self.assertEqual(quote.precio_max, Decimal("430.00"))

    def test_referencias_para_traslado_pequeno_cercano(self):
        cliente = Cliente.objects.create(telefono="51922222225")
        common = {
            "cliente": cliente,
            "tipo_servicio": "mudanza",
            "distrito_origen": "Surco",
            "distrito_destino": "Miraflores",
            "piso_origen": 1,
            "piso_destino": 1,
            "ascensor_origen": False,
            "ascensor_destino": False,
            "camion_llega_origen": True,
            "camion_llega_destino": True,
            "lista_objetos": "escritorio silla PC",
        }

        transport = cotizar_lead(
            Lead.objects.create(
                **common,
                incluye_personal_carga=False,
                modalidad_servicio="sin embalaje",
            )
        )
        personnel = cotizar_lead(
            Lead.objects.create(
                **common,
                incluye_personal_carga=True,
                modalidad_servicio="sin embalaje",
            )
        )
        basic = cotizar_lead(
            Lead.objects.create(
                **common,
                incluye_personal_carga=True,
                modalidad_servicio="embalaje basico",
            )
        )
        furniture = cotizar_lead(
            Lead.objects.create(
                **common,
                incluye_personal_carga=True,
                modalidad_servicio="embalaje de muebles y artefactos",
            )
        )

        self.assertEqual(transport.precio_recomendado, Decimal("150.00"))
        self.assertEqual(personnel.precio_recomendado, Decimal("200.00"))
        self.assertEqual(basic.precio_recomendado, Decimal("350.00"))
        self.assertEqual(furniture.precio_recomendado, Decimal("400.00"))

    def test_historico_reciente_pesa_mas_que_antiguo(self):
        cliente = Cliente.objects.create(telefono="51933333331")
        recent = ServicioHistorico.objects.create(
            fecha=date(2026, 5, 1),
            tipo_servicio="mudanza",
            distrito_origen="Miraflores",
            distrito_destino="Surco",
            piso_origen=2,
            piso_destino=1,
            ascensor_origen=True,
            ascensor_destino=False,
            lista_objetos="cama ropero refrigerador cajas",
            precio_cotizado=Decimal("500.00"),
            precio_final=Decimal("500.00"),
            cerrado=True,
        )
        old = ServicioHistorico.objects.create(
            fecha=date(2024, 1, 1),
            tipo_servicio="mudanza",
            distrito_origen="Miraflores",
            distrito_destino="Surco",
            piso_origen=2,
            piso_destino=1,
            ascensor_origen=True,
            ascensor_destino=False,
            lista_objetos="cama ropero refrigerador cajas",
            precio_cotizado=Decimal("500.00"),
            precio_final=Decimal("500.00"),
            cerrado=True,
        )
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Miraflores",
            distrito_destino="Surco",
            piso_origen=2,
            piso_destino=1,
            ascensor_origen=True,
            ascensor_destino=False,
            lista_objetos="cama ropero refrigerador cajas",
        )
        from apps.cotizador.similarity import score_service as scoring
        recent_score = scoring(lead, recent)
        old_score = scoring(lead, old)
        self.assertGreater(recent_score, old_score)
        self.assertEqual(recent_score, round(17 * 1.0, 2))
        self.assertEqual(old_score, round(17 * 0.25, 2))

    def test_outlier_no_afecta_recomendacion(self):
        cliente = Cliente.objects.create(telefono="51933333332")
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Miraflores",
            distrito_destino="Surco",
            piso_origen=2,
            piso_destino=1,
            ascensor_origen=True,
            ascensor_destino=False,
            lista_objetos="cama ropero refrigerador cajas",
        )
        for price in ["400.00", "410.00", "420.00", "8000.00"]:
            ServicioHistorico.objects.create(
                fecha=date(2026, 5, 1),
                tipo_servicio="mudanza",
                distrito_origen="Miraflores",
                distrito_destino="Surco",
                piso_origen=2,
                piso_destino=1,
                ascensor_origen=True,
                ascensor_destino=False,
                lista_objetos="cama ropero refrigerador cajas",
                precio_cotizado=Decimal(price),
                precio_final=Decimal(price),
                cerrado=True,
            )

        quote = cotizar_lead(lead)

        self.assertEqual(quote.precio_recomendado, Decimal("410.00"))
        self.assertLess(quote.precio_max, Decimal("500.00"))

    def test_menos_de_tres_historicos_usa_fallback(self):
        cliente = Cliente.objects.create(telefono="51933333333")
        Lead.objects.create(
            cliente=cliente,
            tipo_servicio="mudanza",
            distrito_origen="Miraflores",
            distrito_destino="Surco",
        )
        lead = Lead.objects.create(
            cliente=cliente,
            tipo_servicio="otro_servicio",
            distrito_origen="A",
            distrito_destino="B",
        )
        self.assertEqual(lead.cotizaciones.count(), 0)
        quote = cotizar_lead(lead)
        self.assertGreater(quote.precio_recomendado, Decimal("0.00"))
        self.assertIn("reglas base", quote.explicacion.lower())


class AprendizajeTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombre="Cliente Test", telefono="51900000001"
        )

    def _lead_completo(self, **extra):
        defaults = dict(
            cliente=self.cliente,
            tipo_servicio="mudanza",
            distrito_origen="Miraflores",
            distrito_destino="Surco",
            piso_origen=3,
            piso_destino=1,
            ascensor_origen=True,
            ascensor_destino=False,
            modalidad_servicio="embalaje basico",
            incluye_personal_carga=True,
            requiere_desarmado=True,
            lista_objetos="cama ropero refrigerador cajas",
            objetos_pesados="refrigerador",
            peso_carga_kg=Decimal("200.00"),
            volumen_carga_m3=Decimal("4.00"),
            acceso_origen="edificio",
            acceso_destino="casa",
            camion_llega_origen=True,
            camion_llega_destino=True,
            distancia_carga_origen_m=10,
            distancia_carga_destino_m=5,
            tipo_camion="camion 8m",
            capacidad_camion="500 kg",
            precio_final=Decimal("450.00"),
            precio_recomendado=Decimal("500.00"),
            estado=Lead.CERRADO,
            fecha_cierre=timezone.now(),
        )
        defaults.update(extra)
        return Lead.objects.create(**defaults)

    # --- Unit tests: crear_servicio_historico_desde_lead ---

    def test_lead_cerrado_completo_crea_historico(self):
        lead = self._lead_completo()
        historico = crear_servicio_historico_desde_lead(lead)
        self.assertIsNotNone(historico)
        self.assertEqual(historico.lead_origen_id, lead.id)
        self.assertEqual(historico.tipo_servicio, "mudanza")
        self.assertEqual(historico.distrito_origen, "Miraflores")
        self.assertEqual(historico.distrito_destino, "Surco")
        self.assertEqual(historico.piso_origen, 3)
        self.assertEqual(historico.piso_destino, 1)
        self.assertTrue(historico.ascensor_origen)
        self.assertFalse(historico.ascensor_destino)
        self.assertEqual(historico.modalidad_servicio, "embalaje basico")
        self.assertEqual(historico.ayudantes, 1)
        self.assertTrue(historico.requiere_desarmado)
        self.assertIn("cama", historico.lista_objetos)
        self.assertIn("refrigerador", historico.objetos_pesados)
        self.assertEqual(historico.peso_carga_kg, Decimal("200.00"))
        self.assertEqual(historico.volumen_carga_m3, Decimal("4.00"))
        self.assertEqual(historico.acceso_origen, "edificio")
        self.assertEqual(historico.acceso_destino, "casa")
        self.assertTrue(historico.camion_llega_origen)
        self.assertTrue(historico.camion_llega_destino)
        self.assertEqual(historico.distancia_carga_origen_m, 10)
        self.assertEqual(historico.distancia_carga_destino_m, 5)
        self.assertEqual(historico.camion_usado, "camion 8m")
        self.assertEqual(historico.capacidad_camion, "500 kg")
        self.assertEqual(historico.precio_final, Decimal("450.00"))
        self.assertEqual(historico.precio_cotizado, Decimal("500.00"))
        self.assertTrue(historico.cerrado)
        self.assertEqual(historico.fuente, "lead")
        self.assertEqual(historico.referencia_externa, str(lead.id))

    def test_lead_cerrado_sin_precio_no_crea_historico(self):
        lead = self._lead_completo(precio_final=None, precio_recomendado=None)
        historico = crear_servicio_historico_desde_lead(lead)
        self.assertIsNone(historico)
        self.assertEqual(ServicioHistorico.objects.count(), 0)

    def test_lead_cerrado_sin_origen_destino_no_crea_historico(self):
        lead = self._lead_completo(distrito_origen="", distrito_destino="")
        historico = crear_servicio_historico_desde_lead(lead)
        self.assertIsNone(historico)
        self.assertEqual(ServicioHistorico.objects.count(), 0)

    def test_lead_cerrado_sin_tipo_servicio_no_crea_historico(self):
        lead = self._lead_completo(tipo_servicio="")
        historico = crear_servicio_historico_desde_lead(lead)
        self.assertIsNone(historico)
        self.assertEqual(ServicioHistorico.objects.count(), 0)

    def test_lead_no_cerrado_no_crea_historico(self):
        lead = self._lead_completo(estado=Lead.COTIZADO)
        historico = crear_servicio_historico_desde_lead(lead)
        self.assertIsNone(historico)
        self.assertEqual(ServicioHistorico.objects.count(), 0)

    def test_lead_perdido_no_alimenta_historicos(self):
        lead = self._lead_completo(estado=Lead.PERDIDO)
        historico = crear_servicio_historico_desde_lead(lead)
        self.assertIsNone(historico)
        self.assertEqual(ServicioHistorico.objects.count(), 0)

    def test_cerrar_dos_veces_mismo_lead_no_duplica(self):
        lead = self._lead_completo()
        h1 = crear_servicio_historico_desde_lead(lead)
        h2 = crear_servicio_historico_desde_lead(lead)
        self.assertIsNotNone(h1)
        self.assertIsNotNone(h2)
        self.assertEqual(h1.id, h2.id)
        self.assertEqual(ServicioHistorico.objects.count(), 1)

    def test_cambio_precio_final_actualiza_historico(self):
        lead = self._lead_completo()
        h1 = crear_servicio_historico_desde_lead(lead)
        self.assertEqual(h1.precio_final, Decimal("450.00"))

        lead.precio_final = Decimal("500.00")
        lead.save(update_fields=["precio_final"])
        h2 = crear_servicio_historico_desde_lead(lead)
        self.assertEqual(h2.id, h1.id)
        h2.refresh_from_db()
        self.assertEqual(h2.precio_final, Decimal("500.00"))
        self.assertEqual(ServicioHistorico.objects.count(), 1)

    def test_lead_con_precio_recomendado_sin_final_crea_historico(self):
        lead = self._lead_completo(precio_final=None, precio_recomendado=Decimal("480.00"))
        historico = crear_servicio_historico_desde_lead(lead)
        self.assertIsNotNone(historico)
        self.assertIsNone(historico.precio_final)
        self.assertEqual(historico.precio_cotizado, Decimal("480.00"))

    def test_incluye_personal_false_asigna_ayudantes_0(self):
        lead = self._lead_completo(incluye_personal_carga=False)
        historico = crear_servicio_historico_desde_lead(lead)
        self.assertEqual(historico.ayudantes, 0)

    # --- Signal integration tests ---

    def test_signal_crea_historico_al_cerrar_lead(self):
        lead = self._lead_completo(estado=Lead.COTIZADO)
        self.assertEqual(ServicioHistorico.objects.count(), 0)
        lead.estado = Lead.CERRADO
        lead.fecha_cierre = timezone.now()
        lead.save(update_fields=["estado", "fecha_cierre"])
        self.assertEqual(ServicioHistorico.objects.count(), 1)
        historico = ServicioHistorico.objects.get(lead_origen=lead)
        self.assertEqual(historico.tipo_servicio, "mudanza")

    def test_signal_no_dispara_cuando_historico_ya_existe_sin_cambios(self):
        lead = self._lead_completo()
        self.assertEqual(ServicioHistorico.objects.count(), 1)
        lead.save(update_fields=["observaciones"])
        self.assertEqual(ServicioHistorico.objects.count(), 1)

    def test_signal_actualiza_historico_cuando_cambia_precio_final(self):
        lead = self._lead_completo()
        self.assertEqual(ServicioHistorico.objects.get(lead_origen=lead).precio_final, Decimal("450.00"))
        lead.precio_final = Decimal("600.00")
        lead.save(update_fields=["precio_final"])
        self.assertEqual(
            ServicioHistorico.objects.get(lead_origen=lead).precio_final,
            Decimal("600.00"),
        )
