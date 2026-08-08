from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.integrations.enums import InboxStatus, OwnerState, Provider
from apps.integrations.errors import ConversationOwned, IdempotencyConflict
from apps.integrations.models import (
    ConversationControl,
    ConversationTransitionAudit,
    IntegrationInboxEvent,
    IntegrationMessage,
    IntegrationOutboxEvent,
)
from apps.integrations.services.generations import finalize_generation, start_generation
from apps.integrations.services.inbox_outbox import (
    claim_inbox_event,
    claim_outbox_event,
    create_outbox_event,
    recover_inbox_locks,
    recover_outbox_locks,
    register_inbox_event,
)
from apps.integrations.services.state_machine import request_agent, take_conversation
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only concurrency tests.")
@skipUnlessDBFeature("has_select_for_update")
class PostgreSQLConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()
        self.user_ids = [
            user_model.objects.create_user(username="pg_advisor_1").id,
            user_model.objects.create_user(username="pg_advisor_2").id,
        ]
        cliente = Cliente.objects.create(telefono="pg-concurrency-customer")
        self.channel = WhatsAppChannel.objects.create(
            nombre="PG concurrency", phone_number_id="pg-concurrency-phone", activo=True
        )
        lead = Lead.objects.create(cliente=cliente, whatsapp_channel=self.channel)
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=cliente, lead=lead, channel=self.channel
        )
        self.control = ConversationControl.objects.create(conversation=self.conversation)

    def _race(self, operation):
        barrier = Barrier(2, timeout=10)

        def run(index):
            close_old_connections()
            try:
                barrier.wait()
                return operation(index)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run, index) for index in range(2)]
            return [future.result(timeout=20) for future in futures]

    def test_two_advisors_only_one_takes_conversation(self):
        def operation(index):
            actor = get_user_model().objects.get(pk=self.user_ids[index])
            try:
                _, _, changed = take_conversation(
                    self.conversation.id, actor=actor, idempotency_key=f"take-{index}"
                )
                return "changed" if changed else "unchanged"
            except ConversationOwned:
                return "owned"

        self.assertCountEqual(self._race(operation), ["changed", "owned"])
        self.control.refresh_from_db()
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)
        self.assertEqual(self.control.control_version, 1)

    def test_two_generation_finalizations_create_one_output(self):
        generation = start_generation(self.conversation.id, request_key="pg-generation")

        def operation(_index):
            return finalize_generation(generation.id, result_text="Respuesta")[2]

        self.assertCountEqual(self._race(operation), [True, False])
        self.assertEqual(IntegrationMessage.objects.filter(conversation=self.conversation).count(), 1)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(destination=Provider.META_WHATSAPP).count(), 1)

    def test_two_workers_claim_one_inbox_event(self):
        event, _ = register_inbox_event(
            provider=Provider.INTERNAL, event_type="race", idempotency_key="inbox-race", safe_payload={}
        )
        results = self._race(lambda index: bool(claim_inbox_event(event.id, f"worker-{index}")))
        self.assertCountEqual(results, [True, False])

    def test_two_workers_claim_one_outbox_event(self):
        event, _ = create_outbox_event(
            destination=Provider.CHATWOOT, event_type="race", idempotency_key="outbox-race",
            conversation=self.conversation,
        )
        results = self._race(lambda index: bool(claim_outbox_event(event.id, f"worker-{index}")))
        self.assertCountEqual(results, [True, False])

    def test_lock_recovery_only_recovers_expired_locks(self):
        old, _ = register_inbox_event(
            provider=Provider.INTERNAL, event_type="old", idempotency_key="old-lock", safe_payload={}
        )
        current, _ = register_inbox_event(
            provider=Provider.INTERNAL, event_type="current", idempotency_key="current-lock", safe_payload={}
        )
        now = timezone.now()
        IntegrationInboxEvent.objects.filter(pk=old.pk).update(
            status=InboxStatus.PROCESSING, locked_at=now - timedelta(minutes=10), locked_by="old"
        )
        IntegrationInboxEvent.objects.filter(pk=current.pk).update(
            status=InboxStatus.PROCESSING, locked_at=now, locked_by="current"
        )
        self.assertEqual(recover_inbox_locks(now - timedelta(minutes=5)), 1)
        current.refresh_from_db()
        self.assertEqual(current.status, InboxStatus.PROCESSING)

        out_old, _ = create_outbox_event(
            destination=Provider.CHATWOOT, event_type="old", idempotency_key="out-old",
            conversation=self.conversation,
        )
        out_current, _ = create_outbox_event(
            destination=Provider.CHATWOOT, event_type="current", idempotency_key="out-current",
            conversation=self.conversation,
        )
        IntegrationOutboxEvent.objects.filter(pk=out_old.pk).update(
            status="sending", locked_at=now - timedelta(minutes=10), locked_by="old"
        )
        IntegrationOutboxEvent.objects.filter(pk=out_current.pk).update(
            status="sending", locked_at=now, locked_by="current"
        )
        self.assertEqual(recover_outbox_locks(now - timedelta(minutes=5)), 1)
        out_current.refresh_from_db()
        self.assertEqual(out_current.status, "sending")

    def test_same_idempotency_key_and_payload_creates_one_event(self):
        def operation(_index):
            event, created = register_inbox_event(
                provider=Provider.INTERNAL, event_type="same", idempotency_key="same-race",
                safe_payload={"value": 1},
            )
            return str(event.id), created

        results = self._race(operation)
        self.assertEqual(len({item[0] for item in results}), 1)
        self.assertCountEqual([item[1] for item in results], [True, False])

    def test_same_idempotency_key_different_payload_conflicts(self):
        def operation(index):
            try:
                register_inbox_event(
                    provider=Provider.INTERNAL, event_type="different", idempotency_key="different-race",
                    safe_payload={"value": index},
                )
                return "created"
            except IdempotencyConflict:
                return "conflict"

        self.assertCountEqual(self._race(operation), ["created", "conflict"])
        self.assertEqual(IntegrationInboxEvent.objects.filter(idempotency_key="different-race").count(), 1)

    def test_same_external_id_in_different_scopes_is_allowed_concurrently(self):
        def operation(index):
            return str(IntegrationMessage.objects.create(
                conversation=self.conversation, provider=Provider.META_WHATSAPP,
                external_scope=f"phone-{index}", external_message_id="same-external",
                direction="inbound", author_type="customer", idempotency_key="same-key",
            ).id)

        self.assertEqual(len(set(self._race(operation))), 2)

    def test_conditional_unique_constraint_under_race(self):
        def operation(index):
            try:
                IntegrationMessage.objects.create(
                    conversation=self.conversation, provider=Provider.META_WHATSAPP,
                    external_scope="same-phone", external_message_id="duplicate-external",
                    direction="inbound", author_type="customer", idempotency_key=f"key-{index}",
                )
                return "created"
            except IntegrityError:
                return "integrity_error"

        self.assertCountEqual(self._race(operation), ["created", "integrity_error"])

    def test_repeated_transition_does_not_double_increment(self):
        def operation(_index):
            return request_agent(
                self.conversation.id, reason="race", idempotency_key="same-transition"
            )[2]

        self.assertCountEqual(self._race(operation), [True, False])
        self.control.refresh_from_db()
        self.assertEqual(self.control.control_version, 1)
        self.assertEqual(ConversationTransitionAudit.objects.filter(
            conversation=self.conversation, action="request_agent", idempotency_key="same-transition"
        ).count(), 1)
