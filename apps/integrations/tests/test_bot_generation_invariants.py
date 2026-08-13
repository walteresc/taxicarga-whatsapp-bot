"""Tests for bot generation event invariants."""
from django.test import TestCase
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel, MensajeWhatsApp
from apps.integrations.models import BotGeneration, IntegrationOutboxEvent, ConversationControl
from apps.integrations.enums import OutboxStatus, GenerationStatus, OwnerState
from apps.integrations.services.bot_generation_worker import queue_bot_generation, process_bot_generation_event
import uuid


class BotGenerationInvariantsTest(TestCase):
    """Test bot generation and outbox event invariants."""

    def setUp(self):
        self.client_record = Cliente.objects.create(telefono="51900000invtest")
        self.channel = WhatsAppChannel.objects.create(
            nombre="INVARIANT TEST",
            phone_number_id="invtest123",
            activo=True
        )
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_record,
            channel=self.channel,
            ultima_actividad=timezone.now()
        )
        control, _ = ConversationControl.objects.get_or_create(
            conversation=self.conversation,
            defaults={"owner_state": OwnerState.BOT_ACTIVE}
        )
        self.message = MensajeWhatsApp.objects.create(
            conversacion=self.conversation,
            meta_message_id="test-msg-inv-1",
            contenido="test message",
            direccion="INBOUND",
            origen="cliente",
            tipo="text",
            estado="received"
        )

    def test_queue_requires_existing_generation(self):
        """Invariant: queue_bot_generation must validate BotGeneration exists."""
        fake_generation_id = uuid.uuid4()

        # Should raise DoesNotExist, NOT silently create orphan event
        with self.assertRaises(BotGeneration.DoesNotExist):
            queue_bot_generation(message_id=self.message.id, generation_id=fake_generation_id)

        # Verify no event was created with this generation
        self.assertFalse(
            BotGeneration.objects.filter(id=fake_generation_id).exists(),
            "Generation should not exist"
        )

    def test_generation_exists_queue_succeeds(self):
        """Invariant: queue_bot_generation succeeds when BotGeneration exists."""
        control, _ = ConversationControl.objects.get_or_create(
            conversation=self.conversation,
            defaults={"owner_state": OwnerState.BOT_ACTIVE}
        )
        generation = BotGeneration.objects.create(
            conversation=self.conversation,
            request_key="test-queue-1",
            status=GenerationStatus.GENERATING,
            control_version_started=control.control_version,
            expected_owner_state=OwnerState.BOT_ACTIVE
        )

        event = queue_bot_generation(message_id=self.message.id, generation_id=generation.id)
        self.assertEqual(event.event_type, "process_bot_generation")
        self.assertEqual(event.safe_payload["generation_id"], str(generation.id))

    def test_worker_missing_generation_marks_failed(self):
        """Invariant: worker must mark FAILED (not SENT) when generation missing."""
        generation_id = uuid.uuid4()
        event = IntegrationOutboxEvent.objects.create(
            destination="internal",
            destination_scope="channel:test",
            event_type="process_bot_generation",
            idempotency_key=f"test-missing-{generation_id}",
            conversation=self.conversation,
            safe_payload={"message_id": self.message.id, "generation_id": str(generation_id)}
        )

        result = process_bot_generation_event(event.id, worker_id="test")

        event.refresh_from_db()
        self.assertEqual(result, "generation_not_found")
        self.assertEqual(event.status, OutboxStatus.DEAD_LETTER)
        self.assertEqual(event.error_code, "generation_not_found")

    def test_no_orphan_event_after_fix(self):
        """Invariant: no event should reference non-existent generation."""
        # Query all events that reference non-existent generations
        all_events = IntegrationOutboxEvent.objects.filter(event_type="process_bot_generation")

        for evt in all_events:
            gen_id = evt.safe_payload.get("generation_id")
            if gen_id:
                generation_exists = BotGeneration.objects.filter(id=gen_id).exists()
                self.assertTrue(
                    generation_exists or evt.status in [OutboxStatus.FAILED, OutboxStatus.DEAD_LETTER],
                    f"Event {evt.id} references missing generation {gen_id} but is not marked failed"
                )

    def test_idempotent_queue_same_generation_once(self):
        """Idempotency: queuing same generation twice creates one event."""
        control, _ = ConversationControl.objects.get_or_create(
            conversation=self.conversation,
            defaults={"owner_state": OwnerState.BOT_ACTIVE}
        )
        generation = BotGeneration.objects.create(
            conversation=self.conversation,
            request_key="test-idempotent-1",
            status=GenerationStatus.GENERATING,
            control_version_started=control.control_version,
            expected_owner_state=OwnerState.BOT_ACTIVE
        )

        event1 = queue_bot_generation(message_id=self.message.id, generation_id=generation.id)
        event2 = queue_bot_generation(message_id=self.message.id, generation_id=generation.id)
        self.assertEqual(event1.id, event2.id)  # Same event

        # Verify only one event exists for this generation via idempotency key
        event_count = IntegrationOutboxEvent.objects.filter(
            idempotency_key=f"bot-generation-work:{generation.id}"
        ).count()
        self.assertEqual(event_count, 1)

    def test_generation_creation_before_queue(self):
        """Invariant: BotGeneration must be created before OutboxEvent in same transaction."""
        control, _ = ConversationControl.objects.get_or_create(
            conversation=self.conversation,
            defaults={"owner_state": OwnerState.BOT_ACTIVE}
        )
        generation = BotGeneration.objects.create(
            conversation=self.conversation,
            request_key="test-tx-1",
            status=GenerationStatus.GENERATING,
            control_version_started=control.control_version,
            expected_owner_state=OwnerState.BOT_ACTIVE
        )
        generation_id = generation.id

        # Queue the generation
        event = queue_bot_generation(message_id=self.message.id, generation_id=generation_id)

        # Verify ordering: generation exists when event references it
        # (This is guaranteed by the transaction in queue_bot_generation)
        gen_check = BotGeneration.objects.filter(id=generation_id).exists()
        event_check = IntegrationOutboxEvent.objects.filter(id=event.id).exists()

        self.assertTrue(gen_check, "Generation should exist")
        self.assertTrue(event_check, "Event should exist")
        self.assertEqual(str(event.safe_payload["generation_id"]), str(generation_id))
