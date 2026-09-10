import json

from django.test import SimpleTestCase

from apps.agente.registro import catalogo, herramientas_para


class EsquemaTests(SimpleTestCase):
    def test_todas_las_capacidades_tienen_esquema_json_valido(self):
        for c in catalogo():
            e = c.esquema_openai()
            json.dumps(e)  # serializa
            self.assertEqual(e["type"], "function")
            self.assertEqual(e["name"], c.nombre)
            self.assertTrue(e["description"])
            params = e["parameters"]
            self.assertEqual(params["type"], "object")
            self.assertIn("properties", params)
            self.assertFalse(params["additionalProperties"])
            for req in params["required"]:
                self.assertIn(req, params["properties"])

    def test_herramientas_por_perfil(self):
        asesor = {t["name"] for t in herramientas_para("asesor")}
        cliente = {t["name"] for t in herramientas_para("cliente")}
        transportista = {t["name"] for t in herramientas_para("transportista")}
        sistema = {t["name"] for t in herramientas_para("sistema")}

        self.assertEqual(len(sistema), len(catalogo()))       # sistema puede todo
        self.assertLess(cliente, asesor | sistema)            # cliente ⊊
        self.assertNotIn("adjudicar", cliente)
        self.assertNotIn("margen", cliente)
        self.assertNotIn("ver_publicacion", transportista)
        self.assertIn("cargas_disponibles", transportista)
        self.assertIn("ver_carga", cliente)

    def test_enums_declarados(self):
        por_nombre = {c.nombre: c for c in catalogo()}
        self.assertEqual(
            por_nombre["responder_propuesta"].esquema_openai()["parameters"]["properties"]["accion"]["enum"],
            ["aceptar", "contraofertar", "rechazar"],
        )
        self.assertIn(
            "referencial",
            por_nombre["derivar_a_tercerizacion"].esquema_openai()["parameters"]["properties"]["modo_precio"]["enum"],
        )
