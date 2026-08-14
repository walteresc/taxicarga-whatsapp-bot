from django.test import SimpleTestCase

from ..domain.state import Access, BotState
from ..services.conversation_service import ConversationService
from .fakes import ScriptedAgent, output


ROUTES = [
    ("Surco", "Miraflores"), ("Lince", "San Isidro"), ("Barranco", "Chorrillos"),
    ("San Borja", "La Molina"), ("Pueblo Libre", "Magdalena"), ("Breña", "Jesús María"),
    ("Rímac", "Cercado de Lima"), ("Los Olivos", "Independencia"), ("Ate", "Santa Anita"),
    ("Comas", "San Martín de Porres"), ("Surquillo", "Miraflores"), ("San Miguel", "Callao"),
    ("La Victoria", "San Luis"), ("El Agustino", "Ate"), ("Chaclacayo", "Lurigancho"),
    ("Villa El Salvador", "Villa María del Triunfo"), ("San Juan de Miraflores", "Surco"),
    ("Pachacámac", "La Molina"), ("Ancón", "Puente Piedra"),
]


def generic_conversation(origin, destination, index):
    origin_floor = 1 if index % 2 == 0 else 3
    destination_floor = 2 if index % 3 else 1
    route = {"origin_district": origin, "destination_district": destination}
    floors = {"origin_floor": origin_floor, "destination_floor": destination_floor}
    accesses = {}
    if origin_floor > 1:
        accesses["origin_access"] = "ascensor" if index % 4 else "escaleras"
    if destination_floor > 1:
        accesses["destination_access"] = "escaleras" if index % 2 else "ascensor"
    return [
        (f"Quiero mudarme de {origin} a {destination}", output(updates=route, requested=["origin_floor", "destination_floor"])),
        (f"Salgo del {origin_floor} y llego al {destination_floor}", output(updates=floors, requested=list(accesses) or ["items"])),
        ("Hay " + " y ".join(accesses.values()) if accesses else "ambos son primer piso", output(updates=accesses, requested=["items"])),
        (f"Llevo {index + 2} cajas y una cama", output(updates={"items": [f"{index + 2} cajas", "1 cama"]})),
    ]


CANONICAL = [
    ("hola", output(reply="Hola, cuéntame sobre tu mudanza.")),
    ("¿ustedes hacen mudanzas en san isidro?", output(question=True, reply="Sí, hacemos mudanzas en San Isidro. ¿Saldría desde allí?")),
    ("sí, a miraflores", output(updates={"origin_district": "San Isidro", "destination_district": "Miraflores"}, requested=["origin_floor"])),
    ("de primer piso", output(updates={"origin_floor": 1}, requested=["destination_floor"])),
    ("a segundo piso", output(updates={"destination_floor": 2}, requested=["destination_access"])),
    ("escaleras", output(updates={"destination_access": "escaleras"}, requested=["items"])),
    ("1 cama", output(updates={"items": ["1 cama"]}, reply="Perfecto, ya tengo los datos para cotizar.")),
]


class MultiTurnAcceptanceTests(SimpleTestCase):
    def run_conversation(self, turns):
        agent = ScriptedAgent([item[1] for item in turns])
        service = ConversationService(agent)
        state = BotState()
        history = []
        last_bot = ""
        for message, _ in turns:
            result = service.process_turn(
                state=state,
                customer_message=message,
                recent_conversation=history,
                last_bot_message=last_bot,
            )
            self.assertEqual(result.llm_calls, 1)
            state = result.state
            last_bot = result.reply
            history.extend([{"role": "customer", "content": message}, {"role": "assistant", "content": last_bot}])
        return result

    def test_twenty_conversations(self):
        conversations = [CANONICAL] + [generic_conversation(*route, index) for index, route in enumerate(ROUTES, 1)]
        self.assertEqual(len(conversations), 20)
        for index, turns in enumerate(conversations):
            with self.subTest(conversation=index + 1):
                result = self.run_conversation(turns)
                self.assertTrue(result.ready_to_quote)
                self.assertEqual(result.required_missing, [])

    def test_canonical_contextual_confirmation(self):
        result = self.run_conversation(CANONICAL)
        self.assertEqual(result.state.origin_district, "San Isidro")
        self.assertEqual(result.state.destination_district, "Miraflores")
        self.assertEqual(result.state.origin_access, Access.NOT_APPLICABLE)
        self.assertEqual(result.state.destination_access, Access.STAIRS)

    def test_agent_owner_suppresses_bot_without_llm_call(self):
        agent = ScriptedAgent([])
        result = ConversationService(agent).process_turn(
            state=BotState(), customer_message="hola", bot_allowed=False
        )
        self.assertTrue(result.suppressed)
        self.assertEqual(result.llm_calls, 0)

    def test_invalid_requested_field_triggers_one_repair(self):
        agent = ScriptedAgent([
            output(requested=["origin_district"]),
            output(requested=["destination_district"]),
        ])
        state = BotState(origin_district="Surco")
        result = ConversationService(agent).process_turn(state=state, customer_message="hola")
        self.assertEqual(result.llm_calls, 2)
        self.assertIsNotNone(agent.contexts[1][1])

    def test_second_invalid_output_uses_minimal_fallback(self):
        agent = ScriptedAgent([
            output(requested=["origin_district"]),
            output(requested=["origin_district"]),
        ])
        result = ConversationService(agent).process_turn(
            state=BotState(origin_district="Surco"), customer_message="hola"
        )
        self.assertEqual(result.llm_calls, 2)
        self.assertEqual(result.required_missing[0], "destination_district")
        self.assertIn("distrito de destino", result.reply)
