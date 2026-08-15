from django.test import SimpleTestCase

from ..ai.schemas import AgentOutput
from ..domain.state import Access, BotState
from ..domain.merge import merge_state
from ..domain.validators import DomainValidationError
from ..services.conversation_service import ConversationService
from .fakes import ScriptedAgent, output


ROUTES = [
    ("de surco a miraflores", "Surco", "Miraflores"),
    ("surco a miraflores", "Surco", "Miraflores"),
    ("salgo de surco y voy a miraflores", "Surco", "Miraflores"),
    ("de san isidro a la molina", "San Isidro", "La Molina"),
    ("de barranco a san borja", "Barranco", "San Borja"),
    ("salgo de chorrillos hacia surquillo", "Chorrillos", "Surquillo"),
    ("origen pueblo libre destino magdalena", "Pueblo Libre", "Magdalena"),
    ("desde breña hasta lince", "Breña", "Lince"),
    ("de jesús maría a san miguel", "Jesús María", "San Miguel"),
    ("comas a los olivos", "Comas", "Los Olivos"),
    ("de ate a santa anita", "Ate", "Santa Anita"),
    ("salgo de rimac y llego al cercado", "Rímac", "Cercado de Lima"),
    ("villa el salvador a villa maría", "Villa El Salvador", "Villa María del Triunfo"),
    ("de independencia a san martín", "Independencia", "San Martín de Porres"),
    ("la victoria hacia miraflores", "La Victoria", "Miraflores"),
    ("de san luis a surco", "San Luis", "Surco"),
    ("origen callao destino bellavista", "Callao", "Bellavista"),
    ("de chaclacayo a la molina", "Chaclacayo", "La Molina"),
    ("salgo de ancón y voy a puente piedra", "Ancón", "Puente Piedra"),
    ("de carabayllo a comas", "Carabayllo", "Comas"),
]

FLOORS = [
    ("salgo del primero y llego al tercero", {"origin_floor": 1, "destination_floor": 3}),
    ("tercero sin ascensor", {"origin_floor": 3, "origin_access": "escaleras"}),
    ("segundo con ascensor", {"origin_floor": 2, "origin_access": "ascensor"}),
    ("origen piso 4 por escaleras", {"origin_floor": 4, "origin_access": "escaleras"}),
    ("destino quinto con ascensor", {"destination_floor": 5, "destination_access": "ascensor"}),
    ("primer piso a segundo", {"origin_floor": 1, "destination_floor": 2}),
    ("ambos en primer piso", {"origin_floor": 1, "destination_floor": 1}),
    ("salgo del sexto con ascensor", {"origin_floor": 6, "origin_access": "ascensor"}),
    ("llego al cuarto sin ascensor", {"destination_floor": 4, "destination_access": "escaleras"}),
    ("piso dos a piso siete", {"origin_floor": 2, "destination_floor": 7}),
]

ITEMS = [
    ("una cama y 10 cajas", ["cama", "10 cajas"]),
    ("llevo un sofá", ["sofá"]),
    ("refrigeradora y cocina", ["refrigeradora", "cocina"]),
    ("un escritorio y una silla", ["escritorio", "silla"]),
    ("20 cajas y una cómoda", ["20 cajas", "cómoda"]),
    ("lavadora, secadora y cama", ["lavadora", "secadora", "cama"]),
    ("una mesa con seis sillas", ["mesa", "6 sillas"]),
    ("dos roperos", ["2 roperos"]),
    ("televisor y mueble de sala", ["televisor", "mueble de sala"]),
    ("también llevo una refrigeradora", ["refrigeradora"]),
]

MULTI = [
    ("una cama y 10 cajas, salgo del tercero", {"origin_floor": 3, "items": ["cama", "10 cajas"]}),
    ("de surco a miraflores, primero a segundo por escaleras", {"origin_district": "Surco", "destination_district": "Miraflores", "origin_floor": 1, "destination_floor": 2, "destination_access": "escaleras"}),
    ("de Surco a Miraflores, salgo del tercero sin ascensor y llevo una cama", {"origin_district": "Surco", "destination_district": "Miraflores", "origin_floor": 3, "origin_access": "escaleras", "items": ["cama"]}),
    ("san isidro a la molina con 5 cajas", {"origin_district": "San Isidro", "destination_district": "La Molina", "items": ["5 cajas"]}),
    ("salgo del segundo con ascensor y llevo sofá", {"origin_floor": 2, "origin_access": "ascensor", "items": ["sofá"]}),
    ("destino barranco, cuarto piso por escaleras", {"destination_district": "Barranco", "destination_floor": 4, "destination_access": "escaleras"}),
    ("origen surco primer piso y una cama", {"origin_district": "Surco", "origin_floor": 1, "items": ["cama"]}),
    ("de lince a breña con refrigeradora y cocina", {"origin_district": "Lince", "destination_district": "Breña", "items": ["refrigeradora", "cocina"]}),
    ("tercer piso con ascensor hacia miraflores", {"origin_floor": 3, "origin_access": "ascensor", "destination_district": "Miraflores"}),
    ("primero a quinto con ascensor, llevo escritorio", {"origin_floor": 1, "destination_floor": 5, "destination_access": "ascensor", "items": ["escritorio"]}),
]


class ExtractionInvariantTests(SimpleTestCase):
    def test_successful_extraction_logs_raw_output_with_correlation_ids(self):
        agent = ScriptedAgent([output(
            updates={"origin_district": "Surco", "destination_district": "Miraflores"},
            requested=["origin_floor", "destination_floor"], reply="¿En qué pisos?",
        )])
        with self.assertLogs("apps.whatsapp_bot_v4.services.conversation_service", level="INFO") as logs:
            ConversationService(agent).process_turn(
                state=BotState(), customer_message="de surco a miraflores",
                conversation_id=66, message_id=132,
            )
        entry = "\n".join(logs.output)
        self.assertIn("conversation_id=66 message_id=132 attempt=initial", entry)
        self.assertIn("validation=pass", entry)
        self.assertIn('"origin_district":"Surco"', entry)

    def test_response_fallback_has_distinct_warning_and_correlation_ids(self):
        # Scenario: estado completo pero modelo pregunta (premature_question error)
        # Esto NO se resuelve con trim; requiere fallback + WARNING
        complete_state = BotState(
            origin_district="Surco", destination_district="Miraflores",
            origin_floor=2, destination_floor=3,
            origin_access=Access.ELEVATOR, destination_access=Access.STAIRS,
            items=["cama"],
        )
        bad = output(
            updates={},
            requested=["items"], reply="¿Qué más llevas?",  # Error: pregunta cuando ready
        )
        agent = ScriptedAgent([bad, output(requested=["items"], reply="¿Algo más?")])
        with self.assertLogs("apps.whatsapp_bot_v4.services.conversation_service", level="WARNING") as logs:
            ConversationService(agent).process_turn(
                state=complete_state, customer_message="listo",
                conversation_id=66, message_id=132,
            )
        entry = "\n".join(logs.output)
        self.assertIn("bot_v4_response_fallback conversation_id=66 message_id=132", entry)
        self.assertNotIn("bot_v4_minimal_fallback", entry)

    def test_merge_conflict_logs_values_and_complete_updates(self):
        # Comportamiento nuevo: conflictos se aplican con WARNING, no se lanzan
        # Eso permite que correcciones legítimas (re-cotizar con distinto distrito)
        # funcionen sin que el modelo pierda datos en la próxima vuelta
        state = BotState(origin_district="Surco")
        updates = {"origin_district": "Barranco", "destination_district": "Miraflores"}
        with self.assertLogs("apps.whatsapp_bot_v4.domain.merge", level="WARNING") as logs:
            merged = merge_state(state, updates, {})
        # Conflicto debe estar loguado
        entry = logs.output[0]
        self.assertIn("field=origin_district", entry)
        self.assertIn("current='Surco'", entry)
        self.assertIn("Barranco", entry)
        self.assertIn("bot_v4_merge_conflict_apply", entry)
        # Ambos updates deben aplicarse (no se descarta destination por conflicto en origin)
        self.assertEqual(merged.origin_district, "Barranco")
        self.assertEqual(merged.destination_district, "Miraflores")

    def test_50_case_pure_extraction_dataset(self):
        cases = []
        cases.extend((message, {"origin_district": origin, "destination_district": destination}) for message, origin, destination in ROUTES)
        cases.extend(FLOORS)
        cases.extend((message, {"items": items}) for message, items in ITEMS)
        cases.extend(MULTI)
        self.assertEqual(len(cases), 50)
        for message, expected in cases:
            with self.subTest(message=message):
                agent_output = AgentOutput.model_validate(output(
                    updates=expected,
                    requested=["origin_district", "items"],
                    reply="respuesta deliberadamente fuera de foco",
                ))
                merged = ConversationService._validate_extraction(BotState(), agent_output)
                for field, value in expected.items():
                    actual = getattr(merged, field)
                    if field.endswith("_access"):
                        actual = str(actual)
                    self.assertEqual(actual, value)

    def test_last_question_never_filters_route_extraction(self):
        for last_question in ("", "¿Cuál es tu distrito de origen?", "¿Cuál es tu distrito de destino?"):
            with self.subTest(last_question=last_question):
                agent = ScriptedAgent([output(
                    updates={"origin_district": "Surco", "destination_district": "Miraflores"},
                    requested=["origin_floor", "destination_floor"],
                    reply="¿En qué pisos?",
                )])
                result = ConversationService(agent).process_turn(
                    state=BotState(), customer_message="de surco a miraflores",
                    last_bot_message=last_question,
                )
                self.assertEqual((result.state.origin_district, result.state.destination_district), ("Surco", "Miraflores"))
                self.assertEqual(result.llm_calls, 1)

    def test_response_repair_cannot_overwrite_valid_extraction(self):
        # Escenario: estado completo pero modelo pregunta de todas formas
        # Eso lanza "No preguntar más requisitos cuando estado está listo"
        # Repair falla de la misma forma → debe guardar extracción válida, no descartar
        complete_state = BotState(
            origin_district="Surco",
            destination_district="Miraflores",
            origin_floor=2,
            destination_floor=4,
            origin_access=Access.ELEVATOR,
            destination_access=Access.STAIRS,
            items=["cama"],
        )
        agent = ScriptedAgent([
            output(
                updates={},  # No hay updates, estado ya está completo
                requested=["items"], reply="¿Qué más llevas?",  # Error: pregunta cuando ready=True
            ),
            output(
                updates={},  # Repair intenta de nuevo pero sigue preguntando
                requested=["items"], reply="¿Algo más en la mudanza?",
            ),
        ])
        result = ConversationService(agent).process_turn(
            state=complete_state, customer_message="listo para cotizar",
        )
        # Extracción válida debe persistir; reply debe ser fallback (no la pregunta del modelo)
        self.assertEqual(result.state.origin_district, "Surco")
        self.assertEqual(result.state.destination_district, "Miraflores")
        self.assertEqual(result.state.items, ["cama"])
        self.assertTrue(result.ready_to_quote)
        self.assertEqual(result.llm_calls, 2)

    def test_multi_data_is_not_limited_by_question_focus(self):
        agent = ScriptedAgent([output(
            updates={
                "origin_district": "Surco", "destination_district": "Miraflores",
                "origin_floor": 3, "origin_access": "escaleras", "items": ["cama"],
            },
            requested=["destination_floor"], reply="¿A qué piso llega?",
        )])
        result = ConversationService(agent).process_turn(
            state=BotState(),
            customer_message="De Surco a Miraflores, salgo del tercero sin ascensor y llevo una cama",
            last_bot_message="¿Cuál es el origen?",
        )
        self.assertEqual(result.state.origin_district, "Surco")
        self.assertEqual(result.state.destination_district, "Miraflores")
        self.assertEqual(result.state.origin_floor, 3)
        self.assertEqual(result.state.origin_access, Access.STAIRS)
        self.assertEqual(result.state.items, ["cama"])

    def test_strict_mode_does_not_mask_failed_response_repair(self):
        # Escenario: estado completo pero modelo sigue preguntando después de repair fallido
        # Con strict_repairs=True, la excepción no debe ser ocultada
        complete_state = BotState(
            origin_district="Surco",
            destination_district="Miraflores",
            origin_floor=2,
            destination_floor=4,
            origin_access=Access.ELEVATOR,
            destination_access=Access.STAIRS,
            items=["cama"],
        )
        bad_response = output(
            updates={},
            requested=["items"], reply="¿Algún otro artículo?",  # Error: pregunta cuando ready=True
        )
        agent = ScriptedAgent([bad_response, bad_response])
        with self.assertRaises(DomainValidationError):
            ConversationService(agent, strict_repairs=True).process_turn(
                state=complete_state, customer_message="listo",
            )

    def test_production_fallback_logs_structured_anomaly_and_keeps_extraction(self):
        # Scenario: valid extraction but response is premature question (state ready but asking)
        # Must keep extraction, use fallback phrase
        complete_state = BotState(
            origin_district="Surco", destination_district="Miraflores",
            origin_floor=2, destination_floor=4,
            origin_access=Access.ELEVATOR, destination_access=Access.STAIRS,
            items=["cama"],
        )
        bad = output(
            updates={},
            requested=[], reply="¿Seguro que es todo?",  # Premature question: no requested fields but asks with "?"
        )
        agent = ScriptedAgent([bad])
        result = ConversationService(agent).process_turn(
            state=complete_state, customer_message="listo",
        )
        # Extraction was valid (state already complete), should be kept
        self.assertEqual((result.state.origin_district, result.state.destination_district), ("Surco", "Miraflores"))
        # Reply should be fallback (not the premature question)
        self.assertNotIn("¿Seguro", result.reply)

    def test_mixed_logical_groups_auto_trim_without_repair(self):
        # Escenario: modelo emite mezcla de bloques lógicos (origin_floor + items)
        # Trim automático elige el primer grupo con matches (origin_floor)
        # Extracción y reply se preservan, sin necesidad de repair
        agent = ScriptedAgent([
            output(
                updates={"origin_district": "Surco", "destination_district": "Miraflores", "origin_floor": 3},
                requested=["origin_floor", "items"], reply="¿A qué piso llegas?",
            ),
        ])
        with self.assertLogs("apps.whatsapp_bot_v4.services.conversation_service", level="DEBUG") as logs:
            result = ConversationService(agent).process_turn(
                state=BotState(), customer_message="de surco a miraflores, tercer piso",
            )
        entry = "\n".join(logs.output)
        # Log del trim automático debe estar presente
        self.assertIn("bot_v4_requested_fields_trimmed", entry)
        # Extracción debe ser válida
        self.assertEqual(result.state.origin_district, "Surco")
        self.assertEqual(result.state.destination_district, "Miraflores")
        self.assertEqual(result.state.origin_floor, 3)
        # Reply debe ser preservado (no fallback)
        self.assertIn("piso", result.reply)
        # Solo una llamada al agente (sin repair)
        self.assertEqual(result.llm_calls, 1)
