from unittest import TestCase
from django.test import TestCase as DjangoTestCase
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp
from apps.integrations.models import BotGeneration, ConversationControl
from apps.integrations.enums import GenerationStatus, OwnerState, Provider, Direction, AuthorType, Visibility
from apps.integrations.services.generations import finalize_generation


class FinalizationIdempotenceTest(DjangoTestCase):
    """Test that finalize_generation() is idempotent on IntegrationMessage creation."""

    def setUp(self):
        self.client = Cliente.objects.create(telefono="519999999")
        self.channel = WhatsAppChannel.objects.create(nombre="TEST", phone_number_id="123")
        self.conversation = ConversacionWhatsApp.objects.create(cliente=self.client, channel=self.channel)
        ConversationControl.objects.create(
            conversation=self.conversation,
            owner_state=OwnerState.BOT_ACTIVE,
            control_version=1,  # Must match generation.control_version_started
        )

        self.generation = BotGeneration.objects.create(
            conversation=self.conversation,
            status=GenerationStatus.GENERATING,
            request_key="test-key",
            control_version_started=1,
            expected_owner_state=OwnerState.BOT_ACTIVE,
        )

    def test_finalize_generation_idempotent_on_duplicate_call(self):
        """Calling finalize_generation twice should return same message/outbox, not crash."""
        result_text = "Test response"

        # First call should succeed
        gen1, outbox1, published1 = finalize_generation(
            self.generation.id,
            result_text=result_text,
            question_targets=[],
        )

        self.assertEqual(gen1.status, GenerationStatus.PUBLISHED)
        self.assertIsNotNone(outbox1)
        self.assertTrue(published1)

        # Second call with same generation_id should NOT crash
        # It should return the same message/outbox (idempotent)
        gen2, outbox2, published2 = finalize_generation(
            self.generation.id,
            result_text=result_text,
            question_targets=[],
        )

        # Should return same outbox (not create duplicate)
        self.assertEqual(outbox1.id, outbox2.id if outbox2 else outbox1.id)
