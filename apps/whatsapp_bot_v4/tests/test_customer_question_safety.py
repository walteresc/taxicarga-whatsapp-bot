"""
Tests para invariante: customer_question.asked=True NO debe ser degradado a fallback.
Ninguna validación de forma puede reemplazar un reply válido con una plantilla.
"""
from django.test import TestCase

from ..domain.state import BotState
from ..services.conversation_service import ConversationService
from .fakes import ScriptedAgent, output


class CustomerQuestionSafetyTests(TestCase):
    def test_customer_question_asked_preserves_model_reply(self):
        # customer_question.asked=True + estado completo
        # → se envía el reply del modelo, NO el fallback
        agent = ScriptedAgent([
            output(
                updates={"origin_district": "Lima", "destination_district": "Surco",
                         "origin_floor": 1, "destination_floor": 2, "destination_access": "escaleras",
                         "items": ["1 cama"]},
                reply="Sí, podemos agregar embalaje. ¿Quieres embalar todos los muebles?",
                question=True
            )
        ])

        service = ConversationService(agent)
        state = BotState(origin_district="Lima", destination_district="Surco",
                        origin_floor=1, destination_floor=2, destination_access="escaleras",
                        items=["1 cama"])

        result = service.process_turn(
            state=state,
            customer_message="y si deseo embalaje?",
            recent_conversation=[],
            commercial_status="quoted"
        )

        self.assertIn("embalaje", result.reply.lower())
        self.assertNotIn("ya tengo los datos", result.reply.lower())

    def test_empty_requested_fields_with_complete_state(self):
        # requested_fields vacío + estado completo
        # → se envía el reply del modelo (no hay validación que rechace)
        agent = ScriptedAgent([
            output(
                updates={},
                reply="Perfecto. ¿Necesitas algo más?",
                requested=[]
            )
        ])

        service = ConversationService(agent)
        state = BotState(origin_district="Lima", destination_district="Surco",
                        origin_floor=1, destination_floor=2, destination_access="escaleras",
                        items=["1 cama"])

        result = service.process_turn(
            state=state,
            customer_message="gracias",
            recent_conversation=[],
            commercial_status="quoted"
        )

        self.assertEqual(result.reply, "Perfecto. ¿Necesitas algo más?")

    def test_no_customer_question_empty_reply_is_valid(self):
        # Cuando no hay pregunta del cliente y requested_fields está vacío
        # → validación debe pasar, incluso con "?" en reply
        agent = ScriptedAgent([
            output(
                updates={},
                reply="¿Hay algo más que necesites?",
                requested=[]
            )
        ])

        service = ConversationService(agent)
        state = BotState(origin_district="Lima", destination_district="Surco",
                        origin_floor=1, destination_floor=2, destination_access="escaleras",
                        items=["1 cama"])

        result = service.process_turn(
            state=state,
            customer_message="gracias",
            recent_conversation=[],
            commercial_status="quoted"
        )

        # Sin requested_fields, el reply debe preservarse
        self.assertEqual(result.reply, "¿Hay algo más que necesites?")
