import unicodedata

from django.core.management.base import BaseCommand, CommandError

from ...ai.agent import OpenAIConversationAgent
from ...domain.requirements import required_missing
from ...domain.state import BotState
from ...services.conversation_service import ConversationService


CASES = [
    ("de surco a miraflores", {"origin_district": "Surco", "destination_district": "Miraflores"}, ""),
    ("de surco a miraflores", {"origin_district": "Surco", "destination_district": "Miraflores"}, "¿Cuál es tu distrito de origen?"),
    ("de surco a miraflores", {"origin_district": "Surco", "destination_district": "Miraflores"}, "¿Cuál es tu distrito de destino?"),
    ("surco a miraflores", {"origin_district": "Surco", "destination_district": "Miraflores"}, "¿Desde qué distrito sales?"),
    ("salgo de surco y voy a miraflores", {"origin_district": "Surco", "destination_district": "Miraflores"}, "¿Cuál es el origen?"),
    ("de san isidro a la molina", {"origin_district": "San Isidro", "destination_district": "La Molina"}, "¿Cuál es el destino?"),
    ("salgo del primero y llego al tercero", {"origin_floor": 1, "destination_floor": 3}, "¿En qué piso estás?"),
    ("tercero sin ascensor", {"origin_floor": 3, "origin_access": "escaleras"}, "¿En qué piso está el origen?"),
    ("segundo con ascensor", {"destination_floor": 2, "destination_access": "ascensor"}, "¿En qué piso está el destino?"),
    ("una cama y 10 cajas", {"items": ["cama", "10 cajas"]}, "¿Qué cosas llevas?"),
    ("una cama y 10 cajas, salgo del tercero", {"origin_floor": 3, "items": ["cama", "10 cajas"]}, "¿Qué cosas llevas?"),
    ("de surco a miraflores, primero a segundo por escaleras", {"origin_district": "Surco", "destination_district": "Miraflores", "origin_floor": 1, "destination_floor": 2, "destination_access": "escaleras"}, "¿Cuál es el origen?"),
    ("De Surco a Miraflores, salgo del tercero sin ascensor y llevo una cama", {"origin_district": "Surco", "destination_district": "Miraflores", "origin_floor": 3, "origin_access": "escaleras", "items": ["cama"]}, "¿Cuál es el origen?"),
    ("destino barranco, cuarto piso por escaleras", {"destination_district": "Barranco", "destination_floor": 4, "destination_access": "escaleras"}, "¿A dónde llega?"),
    ("origen surco primer piso y una cama", {"origin_district": "Surco", "origin_floor": 1, "items": ["cama"]}, "¿Cuál es el origen?"),
    ("de lince a breña con refrigeradora y cocina", {"origin_district": "Lince", "destination_district": "Breña", "items": ["refrigeradora", "cocina"]}, "¿Desde dónde sales?"),
    ("perdón, el origen es san borja", {"origin_district": "San Borja"}, "¿Cuál es el destino?"),
    ("también llevo una refrigeradora", {"items": ["refrigeradora"]}, "¿En qué piso llega?"),
    ("llego al cuarto sin ascensor y voy a pueblo libre", {"destination_floor": 4, "destination_access": "escaleras", "destination_district": "Pueblo Libre"}, "¿En qué piso llega?"),
    ("salgo del sexto con ascensor, de comas a los olivos, con un sofá", {"origin_floor": 6, "origin_access": "ascensor", "origin_district": "Comas", "destination_district": "Los Olivos", "items": ["sofá"]}, "¿Cuál es el origen?"),
]


def normalize(value):
    if isinstance(value, str):
        return "".join(
            char for char in unicodedata.normalize("NFD", value.lower())
            if unicodedata.category(char) != "Mn"
        ).strip()
    return value


def matches(actual, expected):
    if isinstance(expected, list):
        text = " ".join(normalize(item) for item in (actual or []))
        return all(normalize(item) in text for item in expected)
    return normalize(actual) == normalize(expected)


class Command(BaseCommand):
    help = "Holdout real de extracción V4; no persiste ni envía mensajes."

    def add_arguments(self, parser):
        parser.add_argument("--model", default="gpt-4.1-mini")

    def handle(self, *args, **options):
        agent = OpenAIConversationAgent(model=options["model"])
        passed = true_positive = expected_total = predicted_total = 0
        service_context = ConversationService(None).business_context
        for index, (message, expected, last_bot_message) in enumerate(CASES, 1):
            state = BotState()
            output = agent.respond({
                "goal": "Obtener naturalmente información necesaria para cotizar una mudanza",
                "current_state": state.to_dict(),
                "required_missing": required_missing(state),
                "recent_conversation": [],
                "last_bot_message": last_bot_message,
                "business_context": service_context,
                "customer_message": message,
                "commercial_status": "collecting",
            })
            extracted = output.updates.explicit_values() | output.corrections.explicit_values()
            correct = sum(
                field in extracted and matches(extracted[field], value)
                for field, value in expected.items()
            )
            ok = correct == len(expected)
            passed += int(ok)
            true_positive += correct
            expected_total += len(expected)
            predicted_total += len(extracted)
            self.stdout.write(
                f"CASE {index}: {'PASS' if ok else 'FAIL'}"
                + ("" if ok else f" expected={expected} extracted={extracted}")
            )
        failed = len(CASES) - passed
        precision = true_positive / predicted_total if predicted_total else 0
        recall = true_positive / expected_total if expected_total else 0
        self.stdout.write(
            f"HOLDOUT cases={len(CASES)} passed={passed} failed={failed} "
            f"critical={failed} precision={precision:.4f} recall={recall:.4f}"
        )
        if failed:
            raise CommandError("Critical extraction misses detected.")
