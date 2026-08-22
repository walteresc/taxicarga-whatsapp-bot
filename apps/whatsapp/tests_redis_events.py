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


class TransactionCommitTest(TestCase):
    """Test transaction.on_commit() behavior with event publishing."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user('testuser', 'test@test.com', 'pass123')
        cls.cliente = Cliente.objects.create(
            nombre='Test Cliente',
            telefono='+5199999999'
        )
        cls.channel = WhatsAppChannel.objects.create(
            nombre='Test Channel',
            phone_number_id='test_ch',
            numero_visible='+5199999999',
            activo=True
        )

    def setUp(self):
        """Clear Redis before each test."""
        try:
            bus = RedisEventBus()
            bus.clear()
        except Exception:
            self.skipTest("Redis not available")

    def test_commit_publishes_event(self):
        """Successful transaction publishes event."""
        with transaction.atomic():
            conv = ConversacionWhatsApp.objects.create(
                cliente=self.cliente,
                channel=self.channel
            )

        # Event should be published after commit
        events = get_events(cursor='0')
        event_types = [e.type for e in events]

        self.assertIn('conversation.created', event_types)

    def test_rollback_no_event(self):
        """Rolled back transaction should NOT publish event."""
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
        events = get_events(cursor='0')
        self.assertEqual(len(events), 0)

    def test_event_has_correct_data(self):
        """Event contains correct conversation data."""
        with transaction.atomic():
            conv = ConversacionWhatsApp.objects.create(
                cliente=self.cliente,
                channel=self.channel
            )

        events = get_events(cursor='0')
        self.assertEqual(len(events), 1)

        event = events[0]
        self.assertEqual(event.data['conversation_id'], conv.id)
        self.assertEqual(event.data['cliente_id'], self.cliente.id)
        self.assertEqual(event.data['channel_id'], self.channel.id)


class SSEEndpointTest(TestCase):
    """Test SSE endpoint (real streaming)."""

    @classmethod
    def setUpTestData(cls):
        """Create test user."""
        cls.user = User.objects.create_user('testuser', 'test@test.com', 'pass123')

    def setUp(self):
        """Authenticate and clear events."""
        self.client = Client()
        self.client.login(username='testuser', password='pass123')

        try:
            bus = RedisEventBus()
            bus.clear()
        except Exception:
            self.skipTest("Redis not available")

    def test_sse_endpoint_requires_auth(self):
        """SSE endpoint requires authentication."""
        client = Client()
        response = client.get(reverse('sse-events-stream'))

        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_sse_content_type(self):
        """SSE endpoint returns text/event-stream."""
        response = self.client.get(reverse('sse-events-stream'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/event-stream')

    def test_sse_cache_headers(self):
        """SSE endpoint has correct cache headers."""
        response = self.client.get(reverse('sse-events-stream'), timeout=1)

        self.assertIn('Cache-Control', response)
        self.assertIn('no-cache', response['Cache-Control'])
        self.assertIn('X-Accel-Buffering', response)
        self.assertEqual(response['X-Accel-Buffering'], 'no')

    def test_poll_endpoint_returns_json(self):
        """Poll endpoint (fallback) returns JSON."""
        bus = RedisEventBus()
        bus.publish('test', {'msg': 'hello'})

        response = self.client.get(reverse('api-events-poll'))

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn('events', data)
        self.assertIn('latest_cursor', data)
        self.assertIn('timestamp', data)

    def test_poll_respects_cursor(self):
        """Poll endpoint filters by cursor."""
        bus = RedisEventBus()
        e1 = bus.publish('event1', {})
        e2 = bus.publish('event2', {})

        # Poll with cursor e1.id
        response = self.client.get(
            reverse('api-events-poll'),
            {'cursor': e1.id}
        )

        data = response.json()
        # Should get only e2
        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['events'][0]['id'], e2.id)


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
