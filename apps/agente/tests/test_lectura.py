import json

from django.test import TestCase

from apps.agente.models import AccionAgente
from apps.agente.registro import ejecutar

from ._fixtures import Mundo


class LecturaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.m = Mundo()

    # --- ver_carga ---
    def test_ver_carga_cliente_ve_la_suya(self):
        r = ejecutar("ver_carga", self.m.p_cliente, codigo=self.m.lead.codigo)
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.datos["code"], self.m.lead.codigo)

    def test_ver_carga_cliente_no_ve_la_de_otro(self):
        r = ejecutar("ver_carga", self.m.p_cliente, codigo=self.m.lead2.codigo)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "no_encontrado")

    def test_ver_carga_transportista_sin_datos_del_cliente(self):
        r = ejecutar("ver_carga", self.m.p_carrier, codigo=self.m.publicacion.codigo)
        self.assertTrue(r.ok, r.error)
        blob = json.dumps(r.datos)
        self.assertNotIn("Cliente Dos", blob)
        self.assertNotIn("+51900000102", blob)
        self.assertNotIn("1200", blob)  # precio de venta
        self.assertEqual(r.datos["targetPrice"], 900.0)

    def test_ver_carga_asesor(self):
        r = ejecutar("ver_carga", self.m.p_asesor, codigo=self.m.lead.codigo)
        self.assertTrue(r.ok, r.error)

    # --- ver_negociacion ---
    def test_ver_negociacion_cliente_sin_margen(self):
        r = ejecutar("ver_negociacion", self.m.p_cliente, hilo_id=self.m.hilo_venta.id)
        self.assertTrue(r.ok, r.error)
        self.assertNotIn("margin", json.dumps(r.datos))

    def test_ver_negociacion_cliente_no_ve_hilo_de_compra(self):
        r = ejecutar("ver_negociacion", self.m.p_cliente, hilo_id=self.m.hilo_compra.id)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "no_encontrado")

    def test_ver_negociacion_transportista_solo_la_suya(self):
        r = ejecutar("ver_negociacion", self.m.p_carrier, hilo_id=self.m.hilo_compra.id)
        self.assertTrue(r.ok, r.error)
        r2 = ejecutar("ver_negociacion", self.m.p_carrier2, hilo_id=self.m.hilo_compra.id)
        self.assertFalse(r2.ok)

    def test_ver_negociacion_asesor_sin_rol_margen_no_ve_compra(self):
        r = ejecutar("ver_negociacion", self.m.p_asesor, hilo_id=self.m.hilo_compra.id)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "no_encontrado")

    def test_ver_negociacion_gerente_ve_compra_con_margen(self):
        r = ejecutar("ver_negociacion", self.m.p_gerente, hilo_id=self.m.hilo_compra.id)
        self.assertTrue(r.ok, r.error)
        self.assertIn("margin", r.datos)

    # --- margen ---
    def test_margen_asesor_sin_rol_denegado(self):
        r = ejecutar("margen", self.m.p_asesor, codigo=self.m.lead.codigo)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "fuera_de_alcance")

    def test_margen_gerente_ok(self):
        r = ejecutar("margen", self.m.p_gerente, codigo=self.m.lead.codigo)
        self.assertTrue(r.ok, r.error)
        self.assertIn("sale", r.datos)

    def test_margen_perfil_cliente_no_autorizado(self):
        r = ejecutar("margen", self.m.p_cliente, codigo=self.m.lead.codigo)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "perfil_no_autorizado")

    # --- cargas_del_cliente / cargas_disponibles ---
    def test_cargas_del_cliente(self):
        r = ejecutar("cargas_del_cliente", self.m.p_cliente)
        self.assertTrue(r.ok, r.error)
        self.assertEqual([c["code"] for c in r.datos["resultados"]], [self.m.lead.codigo])

    def test_cargas_disponibles_transportista(self):
        r = ejecutar("cargas_disponibles", self.m.p_carrier)
        self.assertTrue(r.ok, r.error)
        codes = [c["code"] for c in r.datos["resultados"]]
        self.assertIn(self.m.publicacion.codigo, codes)
        self.assertNotIn("Cliente Dos", json.dumps(r.datos))

    def test_cargas_disponibles_perfil_cliente_no_autorizado(self):
        r = ejecutar("cargas_disponibles", self.m.p_cliente)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "perfil_no_autorizado")

    # --- estado_y_seguimiento ---
    def test_estado_y_seguimiento_cliente(self):
        r = ejecutar("estado_y_seguimiento", self.m.p_cliente, codigo=self.m.lead.codigo)
        self.assertTrue(r.ok, r.error)
        self.assertIn(r.datos["estado"], ("negotiating", "quoted", "draft", "booked"))

    # --- ver_cotizacion / ver_reserva / ver_publicacion ---
    def test_ver_cotizacion_cliente(self):
        r = ejecutar("ver_cotizacion", self.m.p_cliente, codigo=self.m.cotizacion.codigo)
        self.assertTrue(r.ok, r.error)

    def test_ver_reserva_asesor(self):
        r = ejecutar("ver_reserva", self.m.p_asesor, codigo=self.m.servicio2.codigo)
        self.assertTrue(r.ok, r.error)

    def test_ver_publicacion_asesor_sin_margen_denegado(self):
        r = ejecutar("ver_publicacion", self.m.p_asesor, codigo=self.m.publicacion.codigo)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo_error, "fuera_de_alcance")

    def test_ver_publicacion_gerente_ok(self):
        r = ejecutar("ver_publicacion", self.m.p_gerente, codigo=self.m.publicacion.codigo)
        self.assertTrue(r.ok, r.error)

    # --- auditoría ---
    def test_toda_lectura_queda_auditada(self):
        AccionAgente.objects.all().delete()
        ejecutar("ver_carga", self.m.p_cliente, codigo=self.m.lead.codigo)
        fila = AccionAgente.objects.get()
        self.assertEqual(fila.capacidad, "ver_carga")
        self.assertTrue(fila.ok)
        self.assertEqual(fila.efecto, "lectura")
        self.assertEqual(fila.lead_id, self.m.lead.id)
