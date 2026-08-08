from datetime import timedelta

from django.utils import timezone

from apps.integrations.enums import GenerationStatus, OwnerState, ResumeMode
from apps.integrations.errors import ConversationOwned, InvalidTransition, VersionConflict
from apps.integrations.models import BotGeneration, ConversationTransitionAudit, IntegrationMessage, IntegrationOutboxEvent
from apps.integrations.services.generations import finalize_generation, start_generation
from apps.integrations.services.state_machine import (
    close_conversation,
    complete_return,
    reopen_conversation,
    request_agent,
    return_to_bot,
    take_conversation,
)

from .base import IntegrationTestCase


class StateMachineTests(IntegrationTestCase):
    def test_full_valid_transition_path(self):
        control, _, changed = request_agent(
            self.conversation.id, reason="special", idempotency_key="request-1", expected_version=0
        )
        self.assertTrue(changed)
        self.assertEqual(control.owner_state, OwnerState.WAITING_AGENT)
        control, _, _ = take_conversation(
            self.conversation.id, actor=self.user, idempotency_key="take-1", expected_version=1
        )
        control, checkpoint, _ = return_to_bot(
            self.conversation.id, actor=self.user, idempotency_key="return-1", expected_version=2
        )
        self.assertEqual(checkpoint.resume_mode, ResumeMode.WAIT_FOR_CUSTOMER)
        control, _, _ = complete_return(checkpoint.id, idempotency_key="complete-1")
        self.assertEqual(control.owner_state, OwnerState.BOT_ACTIVE)
        self.assertEqual(control.control_version, 4)

    def test_idempotent_action_does_not_increment_version(self):
        first, audit, changed = request_agent(
            self.conversation.id, reason="special", idempotency_key="same", expected_version=0
        )
        second, repeated, changed_again = request_agent(
            self.conversation.id, reason="special", idempotency_key="same", expected_version=0
        )
        self.assertTrue(changed)
        self.assertFalse(changed_again)
        self.assertEqual(first.control_version, second.control_version)
        self.assertEqual(audit.id, repeated.id)

    def test_second_advisor_conflicts(self):
        take_conversation(self.conversation.id, actor=self.user, idempotency_key="take-1")
        with self.assertRaises(ConversationOwned):
            take_conversation(self.conversation.id, actor=self.other_user, idempotency_key="take-2")

    def test_version_conflict(self):
        with self.assertRaises(VersionConflict):
            request_agent(self.conversation.id, reason="special", idempotency_key="request", expected_version=99)

    def test_invalid_return_is_rejected(self):
        with self.assertRaises(InvalidTransition):
            return_to_bot(self.conversation.id, actor=self.user, idempotency_key="return")

    def test_inactive_actor_cannot_take_conversation(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        with self.assertRaises(InvalidTransition):
            take_conversation(self.conversation.id, actor=self.user, idempotency_key="take")

    def test_close_and_reopen(self):
        control, _, _ = close_conversation(
            self.conversation.id, reason="done", idempotency_key="close", expected_version=0
        )
        self.assertEqual(control.owner_state, OwnerState.CLOSED)
        control, _, _ = reopen_conversation(
            self.conversation.id, actor=self.user, target=OwnerState.WAITING_AGENT,
            idempotency_key="reopen", expected_version=1,
        )
        self.assertEqual(control.owner_state, OwnerState.WAITING_AGENT)
        self.assertEqual(ConversationTransitionAudit.objects.count(), 2)


class GenerationTests(IntegrationTestCase):
    def test_generation_finishes_to_internal_outbox_only(self):
        generation = start_generation(self.conversation.id, request_key="input-1")
        generation, outbox, published = finalize_generation(generation.id, result_text="Respuesta simulada")
        self.assertTrue(published)
        self.assertEqual(generation.status, GenerationStatus.PUBLISHED)
        self.assertEqual(outbox.status, "pending")

    def test_generation_forbidden_with_advisor(self):
        take_conversation(self.conversation.id, actor=self.user, idempotency_key="take")
        with self.assertRaises(InvalidTransition):
            start_generation(self.conversation.id, request_key="input-1")

    def test_advisor_take_cancels_active_generation(self):
        generation = start_generation(self.conversation.id, request_key="input-1")
        take_conversation(self.conversation.id, actor=self.user, idempotency_key="take")
        generation.refresh_from_db()
        self.assertEqual(generation.status, GenerationStatus.CANCELLED)
        _, outbox, published = finalize_generation(generation.id, result_text="Tardía")
        self.assertFalse(published)
        self.assertIsNone(outbox)

    def test_control_version_change_cancels_finalize(self):
        generation = start_generation(self.conversation.id, request_key="input-1")
        self.control.control_version = 1
        self.control.save(update_fields=["control_version"])
        generation, outbox, published = finalize_generation(generation.id, result_text="Tardía")
        self.assertFalse(published)
        self.assertEqual(generation.status, GenerationStatus.CANCELLED)
        self.assertIsNone(outbox)

    def test_newer_generation_invalidates_older(self):
        older = start_generation(self.conversation.id, request_key="input-old")
        BotGeneration.objects.create(
            conversation=self.conversation, control_version_started=0, request_key="input-new",
            status=GenerationStatus.GENERATING, started_at=timezone.now(),
        )
        older, outbox, published = finalize_generation(older.id, result_text="Antigua")
        self.assertFalse(published)
        self.assertIsNone(outbox)

    def test_duplicate_finalize_creates_one_outbox(self):
        generation = start_generation(self.conversation.id, request_key="input-1")
        finalize_generation(generation.id, result_text="Una")
        _, outbox, published = finalize_generation(generation.id, result_text="Dos")
        self.assertFalse(published)
        self.assertIsNone(outbox)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(destination="meta_whatsapp").count(), 1)

    def test_newer_public_customer_input_invalidates_generation(self):
        original = IntegrationMessage.objects.create(
            conversation=self.conversation, provider="meta_whatsapp", external_scope="phone",
            external_message_id="in-1", direction="inbound", author_type="customer",
            visibility="public", idempotency_key="in-1", received_at=timezone.now() - timedelta(seconds=2),
        )
        generation = start_generation(self.conversation.id, request_key="input-1", input_message=original)
        IntegrationMessage.objects.create(
            conversation=self.conversation, provider="meta_whatsapp", external_scope="phone",
            external_message_id="in-2", direction="inbound", author_type="customer",
            visibility="public", idempotency_key="in-2", received_at=timezone.now(),
        )
        generation, outbox, published = finalize_generation(generation.id, result_text="Tardía")
        self.assertFalse(published)
        self.assertEqual(generation.status, GenerationStatus.CANCELLED)
        self.assertIsNone(outbox)
