from django.test import SimpleTestCase

from ..domain.state import BotState
from ..services.conversation_service import ConversationService
from .fakes import ScriptedAgent, output


CASES = [
    ("hola", {}, {}),
    ("quiero una mudanza", {}, {}),
    ("¿hacen mudanzas en San Isidro?", {}, {}),
    ("salgo de San Isidro", {"origin_district": "San Isidro"}, {"origin_district": "San Isidro"}),
    ("voy a Miraflores", {"destination_district": "Miraflores"}, {"destination_district": "Miraflores"}),
    ("de Surco a Barranco", {"origin_district": "Surco", "destination_district": "Barranco"}, {"origin_district": "Surco", "destination_district": "Barranco"}),
    ("de san isidro a miraflroes", {"origin_district": "San Isidro", "destination_district": "Miraflores"}, {"origin_district": "San Isidro", "destination_district": "Miraflores"}),
    ("salgo del primero", {"origin_floor": 1}, {"origin_floor": 1, "origin_access": "NOT_APPLICABLE"}),
    ("llego al segundo", {"destination_floor": 2}, {"destination_floor": 2}),
    ("origen tercer piso", {"origin_floor": 3}, {"origin_floor": 3}),
    ("ambos son primer piso", {"origin_floor": 1, "destination_floor": 1}, {"origin_floor": 1, "destination_floor": 1, "origin_access": "NOT_APPLICABLE", "destination_access": "NOT_APPLICABLE"}),
    ("salgo del segundo y llego al tercero", {"origin_floor": 2, "destination_floor": 3}, {"origin_floor": 2, "destination_floor": 3}),
    ("hay ascensor en origen", {"origin_access": "ascensor"}, {"origin_access": "ascensor"}),
    ("en destino hay escaleras", {"destination_access": "escaleras"}, {"destination_access": "escaleras"}),
    ("no hay ascensor en origen, solo escaleras", {"origin_access": "escaleras"}, {"origin_access": "escaleras"}),
    ("llevo una cama", {"items": ["1 cama"]}, {"items": ["1 cama"]}),
    ("son diez cajas", {"items": ["10 cajas"]}, {"items": ["10 cajas"]}),
    ("cama, sofá y refrigeradora", {"items": ["cama", "sofá", "refrigeradora"]}, {"items": ["cama", "sofá", "refrigeradora"]}),
    ("San Borja", {"origin_district": "San Borja"}, {"origin_district": "San Borja"}),
    ("a Miraflores", {"destination_district": "Miraflores"}, {"destination_district": "Miraflores"}),
    ("tercero sin ascensor y una cama", {"origin_floor": 3, "origin_access": "escaleras", "items": ["1 cama"]}, {"origin_floor": 3, "origin_access": "escaleras", "items": ["1 cama"]}),
    ("perdón, origen San Borja", {"origin_district": "San Borja"}, {"origin_district": "San Borja"}),
    ("no, llegamos a Barranco", {"destination_district": "Barranco"}, {"destination_district": "Barranco"}),
    ("¿incluyen ayudantes?", {}, {}),
    ("¿cuánto cuesta?", {}, {}),
    ("¿atienden Surco?", {}, {}),
    ("primer piso y 4 cajas", {"origin_floor": 1, "items": ["4 cajas"]}, {"origin_floor": 1, "origin_access": "NOT_APPLICABLE", "items": ["4 cajas"]}),
    ("de Lince a Jesús María, ambos segundo", {"origin_district": "Lince", "destination_district": "Jesús María", "origin_floor": 2, "destination_floor": 2}, {"origin_district": "Lince", "destination_district": "Jesús María", "origin_floor": 2, "destination_floor": 2}),
    ("origen ascensor, destino escaleras", {"origin_access": "ascensor", "destination_access": "escaleras"}, {"origin_access": "ascensor", "destination_access": "escaleras"}),
    ("Necesito mudar una cama de San Isidro a Miraflores. Salgo de primer piso y llego a segundo por escaleras.", {"origin_district": "San Isidro", "destination_district": "Miraflores", "origin_floor": 1, "destination_floor": 2, "destination_access": "escaleras", "items": ["1 cama"]}, {"origin_district": "San Isidro", "destination_district": "Miraflores", "origin_floor": 1, "origin_access": "NOT_APPLICABLE", "destination_floor": 2, "destination_access": "escaleras", "items": ["1 cama"]}),
]


class SingleTurnDatasetTests(SimpleTestCase):
    def test_thirty_cases(self):
        self.assertEqual(len(CASES), 30)
        for message, updates, expected in CASES:
            with self.subTest(message=message):
                agent = ScriptedAgent([output(updates=updates, requested=[])])
                result = ConversationService(agent).process_turn(state=BotState(), customer_message=message)
                for field, value in expected.items():
                    actual = getattr(result.state, field)
                    self.assertEqual(actual, value)
                self.assertEqual(result.llm_calls, 1)

    def test_information_question_does_not_persist_location(self):
        agent = ScriptedAgent([output(question=True, reply="Sí, atendemos San Isidro. ¿La mudanza saldría desde allí?")])
        result = ConversationService(agent).process_turn(state=BotState(), customer_message="¿Atienden San Isidro?")
        self.assertIsNone(result.state.origin_district)
        self.assertIsNone(result.state.destination_district)

    def test_all_data_one_message_ready(self):
        updates = CASES[-1][1]
        result = ConversationService(ScriptedAgent([output(updates=updates)])).process_turn(
            state=BotState(), customer_message=CASES[-1][0]
        )
        self.assertTrue(result.ready_to_quote)

    def test_ready_state_repquestion_is_preserved_when_no_requested(self):
        # Cuando requested_fields está vacío, "?" en reply es válido
        # No se rechaza, no se repara, se preserva el reply
        complete = CASES[-1][1]
        agent = ScriptedAgent([
            output(updates=complete, reply="¿Deseas agregar algo más?"),
        ])
        result = ConversationService(agent).process_turn(state=BotState(), customer_message=CASES[-1][0])
        self.assertTrue(result.ready_to_quote)
        self.assertEqual(result.llm_calls, 1)  # Solo un call, no hay reparación
        self.assertIn("?", result.reply)  # Reply con "?" se preserva
