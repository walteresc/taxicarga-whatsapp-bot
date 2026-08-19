from django.test import TestCase
from apps.whatsapp_bot_v4.services.conversation_service import ConversationService
from apps.whatsapp_bot_v4.ai.agent import OpenAIConversationAgent
from apps.whatsapp_bot_v4.domain.state import BotState


class AccessHallucinationTest(TestCase):
    def setUp(self):
        self.agent = OpenAIConversationAgent()
        self.service = ConversationService(self.agent)

    def test_no_access_mention_clears_hallucination(self):
        """'de 2do piso a 4to piso' → floors 2 y 4, ambos access None"""
        state = BotState(origin_district="Lima", destination_district="La Molina")
        result = self.service.process_turn(
            state=state,
            customer_message="de 2do piso a 4to piso",
            recent_conversation=[],
        )
        self.assertEqual(result.state.origin_floor, 2)
        self.assertEqual(result.state.destination_floor, 4)
        self.assertIsNone(result.state.origin_access)
        self.assertIsNone(result.state.destination_access)

    def test_floor_1_implies_not_applicable(self):
        """'del 1ro al 3ro' → origin_access NOT_APPLICABLE, destination_access None"""
        state = BotState(origin_district="Lima", destination_district="La Molina")
        result = self.service.process_turn(
            state=state,
            customer_message="del 1ro al 3ro",
            recent_conversation=[],
        )
        self.assertEqual(result.state.origin_floor, 1)
        self.assertEqual(result.state.destination_floor, 3)
        self.assertEqual(result.state.origin_access, "NOT_APPLICABLE")
        self.assertIsNone(result.state.destination_access)

    def test_explicit_escaleras_extracted(self):
        """'del 2do sin ascensor al 4to' → origin_access escaleras, destination_access None"""
        state = BotState(origin_district="Lima", destination_district="La Molina")
        result = self.service.process_turn(
            state=state,
            customer_message="del 2do sin ascensor al 4to",
            recent_conversation=[],
        )
        self.assertEqual(result.state.origin_floor, 2)
        self.assertEqual(result.state.destination_floor, 4)
        self.assertEqual(result.state.origin_access, "escaleras")
        self.assertIsNone(result.state.destination_access)

    def test_explicit_ascensor_with_keywords_not_hallucinated(self):
        """'con ascensor' en mensaje → no es hallucination, se permite extracción"""
        state = BotState(origin_district="Lima", destination_district="La Molina")
        result = self.service.process_turn(
            state=state,
            customer_message="del 2do al 4to con ascensor",
            recent_conversation=[],
        )
        self.assertEqual(result.state.origin_floor, 2)
        self.assertEqual(result.state.destination_floor, 4)
        # Momento que explícitamente menciona ascensor no es hallucination
        # Extracción exacta depende del modelo; lo importante es que no es descartada
        self.assertIsNotNone(result.state.origin_access or result.state.destination_access)
