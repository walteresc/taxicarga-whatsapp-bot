"""
Test: Client asks "no veo el costo" when already quoted.
Bug scenario: Bot should respond with price, not fallback.
"""
import logging
import unittest

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp
from ..adapters.crm import CRMV4Adapter
from ..domain.state import BotState
from ..repositories.state import DjangoBotStateRepository
from ..services.conversation_service import ConversationService
from ..services.persistent_conversation_service import PersistentConversationService
from ..services.quote_bridge import QuoteBridge
from ..models import BotConversationState
from ..ai.agent import OpenAIConversationAgent

logger = logging.getLogger(__name__)


class PriceVisibilityBugTest(unittest.TestCase):
    """Test the exact bug scenario: client says 'no veo el costo' when quoted."""

    def setUp(self):
        self.cliente, _ = Cliente.objects.get_or_create(telefono="bug-test")
        self.lead = Lead.objects.create(cliente=self.cliente)
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.cliente, lead=self.lead
        )
        self.conversation_key = f"whatsapp:{self.conversation.pk}"

        self.repository = DjangoBotStateRepository()
        self.repository.reset(self.conversation_key)

    def test_bug_client_asks_for_price_when_already_quoted(self):
        """
        SCENARIO: Estado=QUOTED con quote_price=3500.50
        CLIENTE: "no veo el costo" / "aun no me brinda el precio"
        EXPECTED: Respuesta CON número (3500.50)
        NOT EXPECTED: Fallback "Perfecto, ya tengo los datos"
        """

        initial_state = BotState(
            origin_district="Surco",
            destination_district="Miraflores",
            origin_floor=2,
            destination_floor=4,
        )

        # Setup quoted state with price
        bot_state, _ = BotConversationState.objects.update_or_create(
            conversation_key=self.conversation_key,
            defaults={
                "state_data": initial_state.to_dict(),
                "status": BotConversationState.STATUS_QUOTED,
                "quote_price": 3500.50,
            }
        )

        logger.info("=" * 80)
        logger.info("TEST SETUP: Status=QUOTED, quote_price=3500.50")
        logger.info(f"  conversation_key: {self.conversation_key}")
        logger.info(f"  bot_state.status: {bot_state.status}")
        logger.info(f"  bot_state.quote_price: {bot_state.quote_price}")
        logger.info("=" * 80)

        # Use REAL OpenAI agent (not mocked)
        agent = OpenAIConversationAgent()
        conversation_service = ConversationService(agent)

        persistent_service = PersistentConversationService(
            conversation_service,
            self.repository,
            crm_adapter=CRMV4Adapter(),
            quote_bridge=QuoteBridge(),
        )

        # EXACT BUG SCENARIO: Cliente says "no veo el costo"
        customer_message = "no veo el costo"

        logger.info("=" * 80)
        logger.info(f"SENDING CLIENT MESSAGE: '{customer_message}'")
        logger.info("=" * 80)

        result = persistent_service.process_turn(
            conversation_key=self.conversation_key,
            customer_message=customer_message,
            conversation=self.conversation,
            lead=self.lead,
        )

        logger.info("=" * 80)
        logger.info("RESULT:")
        logger.info(f"  reply: {result.turn.reply}")
        logger.info(f"  ready_to_quote: {result.turn.ready_to_quote}")
        logger.info(f"  conversation_action: {result.turn.conversation_action}")
        logger.info("=" * 80)

        # VERIFY: Reply must contain price number
        self.assertIn(
            "3500",
            result.turn.reply,
            f"❌ BUG REPRODUCED: Reply doesn't contain price.\nReply: {result.turn.reply}"
        )

        # VERIFY: Reply must NOT be the fallback
        self.assertNotEqual(
            result.turn.reply,
            "Perfecto, ya tengo los datos necesarios para preparar la cotización.",
            "❌ BUG: Bot responded with fallback instead of price"
        )

        # VERIFY: Reply has some price-like format
        self.assertTrue(
            any(char.isdigit() for char in result.turn.reply),
            "❌ BUG: Reply has no numbers at all"
        )

        logger.info("✅ BUG TEST PASSED: Client can see the price")

    def test_bug_client_asks_aun_no_me_brinda_precio(self):
        """Alternative phrasing: 'aun no me brinda el precio'"""

        initial_state = BotState(
            origin_district="Lima",
            destination_district="Callao",
            origin_floor=1,
            destination_floor=3,
        )

        bot_state, _ = BotConversationState.objects.update_or_create(
            conversation_key=self.conversation_key,
            defaults={
                "state_data": initial_state.to_dict(),
                "status": BotConversationState.STATUS_QUOTED,
                "quote_price": 2850.00,
            }
        )

        agent = OpenAIConversationAgent()
        conversation_service = ConversationService(agent)

        persistent_service = PersistentConversationService(
            conversation_service,
            self.repository,
            crm_adapter=CRMV4Adapter(),
            quote_bridge=QuoteBridge(),
        )

        customer_message = "aun no me brinda el precio"

        logger.info("=" * 80)
        logger.info(f"VARIANT TEST: '{customer_message}'")
        logger.info("=" * 80)

        result = persistent_service.process_turn(
            conversation_key=self.conversation_key,
            customer_message=customer_message,
            conversation=self.conversation,
            lead=self.lead,
        )

        logger.info(f"  Reply: {result.turn.reply}")

        # Reply must have price
        self.assertIn(
            "2850",
            result.turn.reply,
            f"❌ BUG: Reply doesn't show price 2850.\nReply: {result.turn.reply}"
        )

        logger.info("✅ VARIANT TEST PASSED")
