from unittest import mock

from django.test import TestCase

from apps.agente.models import ConversacionAgente, PropuestaAccion, TurnoAgente
from apps.agente.orquestador import Orquestador
from apps.servicios.models import Servicio

from ._fake_llm import ProviderFake
from ._fixtures import Mundo


def _orq(principal, guion, conversacion=None):
    o = Orquestador(principal, conversacion=conversacion)
    o.provider = ProviderFake(guion)
    return o


class OrquestadorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.m = Mundo()

    def test_lectura_se_ejecuta_y_persiste(self):
        o = _orq(self.m.p_asesor, [
            {"calls": [("ver_carga", {"codigo": self.m.lead.codigo})]},
            {"texto": "La carga va de Miraflores a Surco."},
        ])
        r = o.responder("contame de la carga " + self.m.lead.codigo)
        self.assertIn("Miraflores", r.texto)
        self.assertEqual(r.ejecutadas[0]["capacidad"], "ver_carga")
        self.assertTrue(r.ejecutadas[0]["ok"])
        conv = ConversacionAgente.objects.get(pk=r.conversacion_id)
        self.assertEqual(conv.turnos.count(), 2)
        turno_agente = conv.turnos.get(rol="agente")
        self.assertEqual(turno_agente.tokens_in, 20)  # 2 llamadas × 10

    def test_reversible_se_ejecuta(self):
        o = _orq(self.m.p_asesor, [
            {"calls": [("dejar_nota", {"codigo": self.m.lead.codigo, "texto": "llamar mañana"})]},
            {"texto": "Anoté la nota."},
        ])
        r = o.responder("dejá una nota: llamar mañana")
        self.assertTrue(r.ejecutadas[0]["ok"])
        self.m.lead.refresh_from_db()
        self.assertIn("llamar mañana", self.m.lead.nota_interna)

    def test_critico_se_propone_no_se_ejecuta(self):
        o = _orq(self.m.p_asesor, [
            {"calls": [("cerrar_precio", {"codigo": self.m.lead.codigo, "monto": 850})]},
            {"texto": "Preparé la propuesta de cierre; confirmala vos."},
        ])
        r = o.responder("cerrá el precio en 850")
        self.assertEqual(len(r.propuestas), 1)
        self.assertEqual(r.propuestas[0]["capacidad"], "cerrar_precio")
        self.assertEqual(r.ejecutadas, [])
        prop = PropuestaAccion.objects.get()
        self.assertEqual(prop.estado, "pendiente")
        self.assertIn("850", prop.resumen)
        # no se creó reserva
        self.assertFalse(Servicio.objects.filter(lead_origen=self.m.lead).exists())

    def test_loop_corta_en_max_iter(self):
        # el guión siempre devuelve un call → nunca texto final
        guion = [{"calls": [("ver_carga", {"codigo": self.m.lead.codigo})]}] * 20
        o = _orq(self.m.p_asesor, guion)
        r = o.responder("bucle")
        self.assertEqual(r.iteraciones, Orquestador.MAX_ITER)
        self.assertIn("asesor", r.texto.lower())

    def test_capacidad_fuera_de_perfil_no_crashea(self):
        # el modelo "pide" adjudicar siendo cliente → el orquestador lo bloquea
        o = _orq(self.m.p_cliente, [
            {"calls": [("adjudicar", {"publicacion_codigo": "F01", "oferta_id": 1})]},
            {"texto": "No puedo hacer eso."},
        ])
        r = o.responder("adjudicá F01")
        self.assertEqual(r.ejecutadas, [])
        self.assertEqual(r.propuestas, [])

    def test_cliente_solo_recibe_tools_de_su_perfil(self):
        from apps.agente.registro import herramientas_para
        nombres = {t["name"] for t in herramientas_para("cliente")}
        self.assertIn("ver_carga", nombres)
        self.assertNotIn("adjudicar", nombres)
        self.assertNotIn("margen", nombres)

    def test_continua_conversacion(self):
        o1 = _orq(self.m.p_asesor, [{"texto": "Hola, ¿en qué te ayudo?"}])
        r1 = o1.responder("hola")
        conv = ConversacionAgente.objects.get(pk=r1.conversacion_id)
        o2 = _orq(self.m.p_asesor, [{"texto": "Seguimos."}], conversacion=conv)
        r2 = o2.responder("seguime")
        self.assertEqual(r2.conversacion_id, conv.id)
        self.assertEqual(conv.turnos.count(), 4)
