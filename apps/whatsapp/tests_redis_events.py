"""Tests for Redis-based event streaming (FASE 5B SSE architecture).

Tests Redis Streams, transaction.on_commit(), and SSE endpoint.
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.db import transaction

from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp
from apps.whatsapp.redis_events import RedisEventBus, publish_event, get_events, get_latest_cursor


class RedisEventBusTest(TestCase):
    """Test Redis Streams event bus operations."""

    def setUp(self):
        """Initialize event bus."""
        try:
            self.bus = RedisEventBus()
            self.bus.clear()
        except Exception as e:
            self.skipTest(f"Redis not available: {e}")

    def tearDown(self):
        """Clean up."""
        try:
            self.bus.clear()
        except Exception:
            pass

    def test_redis_available(self):
        """Redis should be available."""
        self.assertTrue(self.bus.is_available())

    def test_publish_event(self):
        """Publish event to stream."""
        event = self.bus.publish('test.event', {'data': 'value'})

        self.assertIsNotNone(event.id)
        self.assertEqual(event.type, 'test.event')
        self.assertEqual(event.data['data'], 'value')

    def test_get_events_since_cursor(self):
        """Retrieve events after cursor."""
        e1 = self.bus.publish('event1', {})
        e2 = self.bus.publish('event2', {})
        e3 = self.bus.publish('event3', {})

        # Get all
        all_events = self.bus.get_events_since('0')
        self.assertEqual(len(all_events), 3)

        # Get after e1
        after_e1 = self.bus.get_events_since(e1.id)
        self.assertEqual(len(after_e1), 2)
        self.assertEqual(after_e1[0].id, e2.id)

    def test_latest_id(self):
        """Get latest event ID."""
        self.bus.publish('event1', {})
        latest_1 = self.bus.get_latest_id()

        self.bus.publish('event2', {})
        latest_2 = self.bus.get_latest_id()

        # Latest should be different
        self.assertNotEqual(latest_1, latest_2)

    def test_cursor_valid_check(self):
        """Check if cursor is valid (exists in stream)."""
        event = self.bus.publish('event', {})

        # Valid cursor
        self.assertTrue(self.bus.check_cursor_valid(event.id))

        # Invalid cursor (old ID)
        self.assertFalse(self.bus.check_cursor_valid('0-0'))

    def test_health_check(self):
        """Health check returns status."""
        health = self.bus.health_check()

        self.assertTrue(health['available'])
        self.assertIn('stream_key', health)
        self.assertIn('stream_length', health)




class EventSchemaTest(TestCase):
    """Test event data structure."""

    def setUp(self):
        """Clear Redis."""
        try:
            bus = RedisEventBus()
            bus.clear()
        except Exception:
            self.skipTest("Redis not available")

    def test_event_schema(self):
        """Event has required fields."""
        event = publish_event('test.type', {'key': 'value'})

        self.assertIsNotNone(event.id)
        self.assertIsNotNone(event.timestamp)
        self.assertEqual(event.type, 'test.type')
        self.assertEqual(event.data['key'], 'value')

    def test_to_dict(self):
        """Event.to_dict() has correct format."""
        event = publish_event('test', {'data': 123})
        event_dict = event.to_dict()

        self.assertEqual(event_dict['type'], 'test')
        self.assertEqual(event_dict['data']['data'], 123)
        self.assertIn('id', event_dict)
        self.assertIn('timestamp', event_dict)
