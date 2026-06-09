from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from apps.clientes.models import Cliente
from apps.cotizador.models import Cotizacion, ServicioHistorico
from apps.cotizador.services import cotizar_lead
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

        self.assertEqual(quote.precio_recomendado, Decimal("425.00"))
        self.assertLess(quote.precio_max, Decimal("2500.00"))

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
