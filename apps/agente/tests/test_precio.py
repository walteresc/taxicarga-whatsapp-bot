from django.test import TestCase

from apps.agente.registro import ejecutar

from ._fixtures import Mundo


class PrecioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.m = Mundo()

    def test_calcular_precio_mudanza_lima(self):
        r = ejecutar("calcular_precio", self.m.p_asesor, codigo=self.m.lead.codigo)
        self.assertTrue(r.ok, r.error)
        self.assertIn(r.datos["modo"], ("automatico", "manual"))
        if r.datos["modo"] == "automatico":
            self.assertGreater(r.datos["recomendado"], 0)

    def test_calcular_precio_interprovincial_es_manual(self):
        self.m.lead.es_interprovincial = True
        self.m.lead.save(update_fields=["es_interprovincial"])
        self.m.lead.cotizaciones.all().delete()
        r = ejecutar("calcular_precio", self.m.p_asesor, codigo=self.m.lead.codigo)
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.datos["modo"], "manual")

    def test_calcular_precio_cliente_ve_la_suya(self):
        r = ejecutar("calcular_precio", self.m.p_cliente, codigo=self.m.lead.codigo)
        self.assertTrue(r.ok, r.error)

    def test_calcular_precio_perfil_transportista_no_autorizado(self):
        r = ejecutar("calcular_precio", self.m.p_carrier, codigo=self.m.lead.codigo)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "perfil_no_autorizado")

    def test_sugerir_precio_cierre(self):
        r = ejecutar("sugerir_precio_cierre", self.m.p_asesor, codigo=self.m.lead.codigo)
        self.assertTrue(r.ok, r.error)
        d = r.datos
        self.assertEqual(d["contraoferta_cliente"], 800.0)
        self.assertGreaterEqual(d["sugerencia"], d["piso_tecnico"])
        self.assertIn("motivo", d)

    def test_sugerir_precio_cierre_no_lo_ve_el_cliente(self):
        r = ejecutar("sugerir_precio_cierre", self.m.p_cliente, codigo=self.m.lead.codigo)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "perfil_no_autorizado")
