from django.core.management import call_command
from django.test import TestCase

from apps.agente.conocimiento import buscar
from apps.agente.models import DocumentoConocimiento
from apps.agente.registro import ejecutar

from ._fixtures import Mundo


class ConocimientoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.m = Mundo()
        DocumentoConocimiento.objects.create(
            slug="cobertura", titulo="Cobertura", categoria="empresa",
            visibilidad="publico", contenido="Lima Metropolitana y Callao.",
        )
        DocumentoConocimiento.objects.create(
            slug="margenes", titulo="Márgenes", categoria="precios",
            visibilidad="interno", contenido="El margen solo lo ve Gerencia.",
        )
        DocumentoConocimiento.objects.create(
            slug="inactivo", titulo="Viejo", categoria="empresa",
            visibilidad="publico", contenido="cobertura antigua", activo=False,
        )

    def test_buscar_publico_no_trae_internos(self):
        docs = buscar("margen cobertura", incluir_internos=False)
        slugs = {d.slug for d in docs}
        self.assertIn("cobertura", slugs)
        self.assertNotIn("margenes", slugs)
        self.assertNotIn("inactivo", slugs)

    def test_buscar_interno_trae_todo(self):
        docs = buscar("margen", incluir_internos=True)
        self.assertIn("margenes", {d.slug for d in docs})

    def test_capacidad_cliente_solo_publico(self):
        r = ejecutar("consultar_conocimiento", self.m.p_cliente, tema="cobertura margen")
        self.assertTrue(r.ok, r.error)
        titulos = {d["titulo"] for d in r.datos["documentos"]}
        self.assertIn("Cobertura", titulos)
        self.assertNotIn("Márgenes", titulos)

    def test_capacidad_asesor_ve_internos(self):
        r = ejecutar("consultar_conocimiento", self.m.p_asesor, tema="margen")
        self.assertIn("Márgenes", {d["titulo"] for d in r.datos["documentos"]})

    def test_capacidad_transportista_puede_consultar(self):
        r = ejecutar("consultar_conocimiento", self.m.p_carrier, tema="cobertura")
        self.assertTrue(r.ok, r.error)

    def test_sin_resultado(self):
        r = ejecutar("consultar_conocimiento", self.m.p_cliente, tema="xyzzy inexistente")
        self.assertTrue(r.ok)
        self.assertFalse(r.datos["encontrado"])

    def test_seed_es_idempotente(self):
        call_command("seed_conocimiento")
        n = DocumentoConocimiento.objects.count()
        call_command("seed_conocimiento")
        self.assertEqual(DocumentoConocimiento.objects.count(), n)
