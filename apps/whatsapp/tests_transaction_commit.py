"""Tests for transaction.on_commit() behavior (FASE 5B post-commit events)."""

from django.test import TestCase, TransactionTestCase
from django.db import transaction
from django.contrib.auth.models import User

from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp
from apps.whatsapp.redis_events import RedisEventBus


class TransactionCommitCallbackTest(TransactionTestCase):
    """Test transaction.on_commit() callbacks (must use TransactionTestCase)."""

    def setUp(self):
        """Setup test data."""
        try:
            self.bus = RedisEventBus()
            self.bus.clear()
        except Exception:
            self.skipTest("Redis not available")

        self.cliente = Cliente.objects.create(
            nombre='Test Cliente',
            telefono='+5199999999'
        )
        self.channel = WhatsAppChannel.objects.create(
            nombre='Test Channel',
            phone_number_id='test_ch',
            numero_visible='+5199999999',
            activo=True
        )

    def test_commit_publishes_event(self):
        """Successful commit should trigger event publish."""
        with transaction.atomic():
            conv = ConversacionWhatsApp.objects.create(
                cliente=self.cliente,
                channel=self.channel
            )

        # Event should be in Redis after commit
        events = self.bus.get_events_since('0')
        self.assertGreater(len(events), 0)

        event_types = [e.type for e in events]
        self.assertIn('conversation.created', event_types)

    def test_rollback_no_event(self):
        """Rollback should NOT publish event."""
        try:
            with transaction.atomic():
                conv = ConversacionWhatsApp.objects.create(
                    cliente=self.cliente,
                    channel=self.channel
                )
                # Force rollback
                raise Exception("Intentional rollback")
        except Exception:
            pass

        # No event should be published
        events = self.bus.get_events_since('0')
        self.assertEqual(len(events), 0)

    def test_event_published_only_once(self):
        """Creating one conversation should publish exactly one event."""
        with transaction.atomic():
            conv = ConversacionWhatsApp.objects.create(
                cliente=self.cliente,
                channel=self.channel
            )

        events = self.bus.get_events_since('0')

        # Should be exactly 1 event
        self.assertEqual(len(events), 1)

        event = events[0]
        self.assertEqual(event.type, 'conversation.created')
        self.assertEqual(event.data['conversation_id'], conv.id)

    def test_multiple_transactions_separate_events(self):
        """Multiple transactions should generate separate events."""
        with transaction.atomic():
            conv1 = ConversacionWhatsApp.objects.create(
                cliente=self.cliente,
                channel=self.channel
            )

        # Should have 1 event now
        events1 = self.bus.get_events_since('0')
        self.assertEqual(len(events1), 1)

        # Create second cliente+channel to avoid UNIQUE constraint
        cliente2 = Cliente.objects.create(
            nombre='Test Cliente 2',
            telefono='+5199999991'
        )

        # Second conversation with different cliente
        with transaction.atomic():
            conv2 = ConversacionWhatsApp.objects.create(
                cliente=cliente2,
                channel=self.channel
            )

        # Should have 2 events now
        events2 = self.bus.get_events_since('0')
        self.assertEqual(len(events2), 2)

    def test_nested_transaction_commit(self):
        """Nested transaction should still publish on outer commit."""
        with transaction.atomic():
            with transaction.atomic(savepoint=True):
                conv = ConversacionWhatsApp.objects.create(
                    cliente=self.cliente,
                    channel=self.channel
                )

        # Event should be published
        events = self.bus.get_events_since('0')
        self.assertGreater(len(events), 0)

    def test_partial_rollback_no_event(self):
        """Savepoint rollback should not publish event."""
        with transaction.atomic():
            try:
                with transaction.atomic(savepoint=True):
                    conv = ConversacionWhatsApp.objects.create(
                        cliente=self.cliente,
                        channel=self.channel
                    )
                    raise Exception("Savepoint rollback")
            except Exception:
                pass

            # Outer transaction continues
            conv2 = ConversacionWhatsApp.objects.create(
                cliente=self.cliente,
                channel=self.channel
            )

        # Only one event (for conv2)
        events = self.bus.get_events_since('0')
        event_data = [e.data for e in events]

        # Should have event for conv2
        conv2_events = [e for e in event_data if e.get('conversation_id') == conv2.id]
        self.assertEqual(len(conv2_events), 1)


class EventDataCompletnessTest(TransactionTestCase):
    """Test that events contain complete, up-to-date data (must use TransactionTestCase)."""

    def setUp(self):
        """Setup."""
        try:
            bus = RedisEventBus()
            bus.clear()
        except Exception:
            self.skipTest("Redis not available")

        self.cliente = Cliente.objects.create(
            nombre='Test Cliente Data',
            telefono='+5199999998'
        )
        self.channel = WhatsAppChannel.objects.create(
            nombre='Test Channel Data',
            phone_number_id='test_ch_data',
            numero_visible='+5199999998',
            activo=True
        )

    def test_event_has_conversation_data(self):
        """Event should include current conversation state."""
        with transaction.atomic():
            conv = ConversacionWhatsApp.objects.create(
                cliente=self.cliente,
                channel=self.channel,
                resumen='Test summary'
            )

        events = RedisEventBus().get_events_since('0')
        event = events[0]

        # Verify event data
        self.assertEqual(event.data['conversation_id'], conv.id)
        self.assertEqual(event.data['cliente_id'], self.cliente.id)
        self.assertEqual(event.data['channel_id'], self.channel.id)

    def test_event_timestamp_set(self):
        """Event should have timestamp."""
        with transaction.atomic():
            conv = ConversacionWhatsApp.objects.create(
                cliente=self.cliente,
                channel=self.channel
            )

        events = RedisEventBus().get_events_since('0')
        event = events[0]

        self.assertIsNotNone(event.timestamp)
        # Should be ISO format
        self.assertIn('T', event.timestamp)
        self.assertIn('Z', event.timestamp)
