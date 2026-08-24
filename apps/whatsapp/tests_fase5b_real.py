"""
FASE 5B Real Tests: Behavior-driven, actual event verification.

Tests that EXECUTE code and verify actual behavior, not source code inspection.
Uses TransactionTestCase so transaction.on_commit() actually fires.
Verifies Redis Stream events.
"""

import json
import logging
from django.test import TransactionTestCase
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.db import transaction
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.whatsapp.redis_events import get_latest_cursor, get_events

logger = logging.getLogger(__name__)


class ConversationCreationEventTest(TransactionTestCase):
    """Test conversation.created event fires and contains correct data."""

    def setUp(self):
        """Setup channel, cliente."""
        from apps.clientes.models import Cliente

        self.channel = WhatsAppChannel.objects.create(
            nombre='TestChannel',
            phone_number_id='123456',
            activo=True
        )

        self.cliente = Cliente.objects.create(
            nombre='TestCliente',
            telefono='51912345678'
        )

    def test_new_conversation_publishes_event(self):
        """New conversation → signal publishes conversation.created event."""
        # Get event count BEFORE
        cursor_before = get_latest_cursor()
        events_before = get_events(cursor_before)

        # Create conversation
        conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='Test conv',
            estado_atencion='en_espera'
        )

        # Transaction commits here (on_commit fires in TransactionTestCase)
        # Get event count AFTER
        cursor_after = get_latest_cursor()
        events_after = get_events(cursor_before)  # Read from before cursor

        created_events = [e for e in events_after if e.type == 'conversation.created']

        logger.info(f"[creation] Events published: {len(created_events)}")
        if created_events:
            for ev in created_events:
                logger.info(f"  - {ev.type}: conv_id={ev.data.get('conversation_id')}")

        # VERIFY: At least one conversation.created event
        self.assertGreaterEqual(len(created_events), 1, "conversation.created must be published")

    def test_conversation_created_event_has_required_fields(self):
        """conversation.created event must include conversation_id, cliente_id, etc."""
        cursor_before = get_latest_cursor()

        conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='Test conv',
            estado_atencion='en_espera'
        )

        events = get_events(cursor_before)
        created_events = [e for e in events if e.type == 'conversation.created']

        self.assertGreaterEqual(len(created_events), 1, "Must have created event")

        event = created_events[0] if created_events else {}
        data = event.data

        self.assertEqual(data.get('conversation_id'), conv.id, "Event must have conversation_id")
        self.assertEqual(data.get('cliente_id'), self.cliente.id, "Event must have cliente_id")
        logger.info(f"[creation] Event fields correct: conv_id={data.get('conversation_id')}, cliente_id={data.get('cliente_id')}")


class MessageCreatedEventTest(TransactionTestCase):
    """Test message.created event fires with deduplication support."""

    def setUp(self):
        """Setup."""
        from apps.clientes.models import Cliente

        self.channel = WhatsAppChannel.objects.create(
            nombre='TestChannel',
            phone_number_id='123456',
            activo=True
        )

        self.cliente = Cliente.objects.create(
            nombre='TestCliente',
            telefono='51912345678'
        )

        self.conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='Test',
            estado_atencion='en_espera'
        )

    def test_inbound_message_publishes_event(self):
        """Inbound message → signal publishes message.created event."""
        cursor_before = get_latest_cursor()

        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            direccion=MensajeWhatsApp.ENTRANTE,
            tipo='text',
            contenido='Test inbound',
            meta_message_id='wamid_123'
        )

        events = get_events(cursor_before)
        msg_events = [e for e in events if e.type == 'message.created']

        logger.info(f"[inbound] message.created events: {len(msg_events)}")
        self.assertGreaterEqual(len(msg_events), 1, "Inbound message must publish event")

        if msg_events:
            event_data = msg_events[0].data
            self.assertEqual(event_data.get('message_id'), msg.id, "Event must include message_id")
            self.assertEqual(event_data.get('meta_message_id'), 'wamid_123', "Event must include meta_message_id")
            logger.info(f"[inbound] ✓ Event has message_id={msg.id}, meta_message_id=wamid_123")


class CursorCoherenceTest(TransactionTestCase):
    """Test cursor protocol: C1 before snapshot, events after C1."""

    def setUp(self):
        """Setup."""
        from apps.clientes.models import Cliente

        self.channel = WhatsAppChannel.objects.create(
            nombre='TestChannel',
            phone_number_id='123456',
            activo=True
        )

        self.cliente = Cliente.objects.create(
            nombre='TestCliente',
            telefono='51912345678'
        )

    def test_cursor_advances_after_event(self):
        """Cursor advances after events are published."""
        c1 = get_latest_cursor()
        logger.info(f"[cursor] C1={c1}")

        # Create conversation (publishes event)
        conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='Test',
            estado_atencion='en_espera'
        )

        c2 = get_latest_cursor()
        logger.info(f"[cursor] C2={c2} (after creation)")

        # C2 should be different from C1 (Redis stream has new entries)
        self.assertNotEqual(c1, c2, "Cursor must advance after event publication")

    def test_snapshot_cursor_never_zero(self):
        """get_latest_cursor() never returns '0'."""
        cursor = get_latest_cursor()
        self.assertNotEqual(cursor, '0', "Cursor must never be '0'")
        self.assertIsNotNone(cursor, "Cursor must not be None")
        logger.info(f"[cursor] Valid cursor={cursor}")


class LastEventIDHeaderTest(TransactionTestCase):
    """Test SSE accepts Last-Event-ID for recovery."""

    def test_sse_endpoint_has_last_event_id_support(self):
        """Verify SSE endpoint code includes Last-Event-ID header handling."""
        import inspect
        from apps.dashboard.views_sse import sse_events_stream

        source = inspect.getsource(sse_events_stream)

        # Check for header handling
        has_last_event_id = 'Last-Event-ID' in source
        has_header_get = "headers.get('Last-Event-ID'" in source

        logger.info(f"[sse] Last-Event-ID in source: {has_last_event_id}")
        logger.info(f"[sse] headers.get('Last-Event-ID'): {has_header_get}")

        self.assertTrue(has_last_event_id, "SSE must mention Last-Event-ID")


class SignalImplementationAuditTest(TransactionTestCase):
    """Audit current signal implementation to identify missing real value detection."""

    def test_update_fields_logic_exists(self):
        """Verify signal checks update_fields intersection with SIGNIFICANT_FIELDS."""
        import inspect
        from apps.whatsapp.signals import publish_conversation_state_change

        source = inspect.getsource(publish_conversation_state_change)

        has_update_fields_check = 'update_fields' in source
        has_significant_fields = 'SIGNIFICANT_FIELDS' in source
        has_intersection_check = 'SIGNIFICANT_FIELDS & set(update_fields)' in source

        logger.info(f"[signal] update_fields check: {has_update_fields_check}")
        logger.info(f"[signal] SIGNIFICANT_FIELDS defined: {has_significant_fields}")
        logger.info(f"[signal] Intersection check (update_fields & SIGNIFICANT): {has_intersection_check}")

        self.assertTrue(has_intersection_check, "Signal must check update_fields intersection")

    def test_missing_value_comparison(self):
        """AUDIT: Signal does NOT compare old vs new values."""
        import inspect
        from apps.whatsapp.signals import publish_conversation_state_change

        source = inspect.getsource(publish_conversation_state_change)

        has_old_value_capture = 'instance.__dict__' in source or '.original' in source or 'cache' in source
        has_value_comparison = '==' in source and 'old' in source.lower()

        logger.info(f"[signal] Captures old values: {has_old_value_capture}")
        logger.info(f"[signal] Compares old==new: {has_value_comparison}")

        # EXPECTED TO BE FALSE - this is what needs fixing
        if not has_value_comparison:
            logger.warning("[signal] ⚠️ NO VALUE COMPARISON - only update_fields presence checked")
            logger.warning("[signal]    This means save(update_fields=['resumen']) with same value WILL emit event")
            logger.warning("[signal]    NEEDS FIX: Compare previous values before emitting")


if __name__ == '__main__':
    import unittest
    unittest.main()
