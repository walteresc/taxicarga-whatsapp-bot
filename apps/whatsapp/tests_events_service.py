"""Tests for event streaming service (FASE 5B)."""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp.events_service import publish_event, get_events, get_latest_cursor, _reset_for_testing


class EventBusTest(TestCase):
    """Test event bus core functionality."""

    def setUp(self):
        """Reset event bus before each test."""
        _reset_for_testing()

    def test_publish_and_retrieve(self):
        """Publish event and retrieve it."""
        event = publish_event('test_event', {'data': 'value'})

        self.assertEqual(event.type, 'test_event')
        self.assertEqual(event.data, {'data': 'value'})
        self.assertIsNotNone(event.timestamp)

    def test_cursor_pagination(self):
        """Retrieve events after cursor."""
        _reset_for_testing()

        # Publish 3 events
        e1 = publish_event('event1', {'n': 1})
        e2 = publish_event('event2', {'n': 2})
        e3 = publish_event('event3', {'n': 3})

        # Get all (cursor=0)
        all_events = get_events(cursor=0)
        self.assertEqual(len(all_events), 3)

        # Get after first event
        after_e1 = get_events(cursor=e1.id)
        self.assertEqual(len(after_e1), 2)
        self.assertEqual(after_e1[0].id, e2.id)

        # Get after second event
        after_e2 = get_events(cursor=e2.id)
        self.assertEqual(len(after_e2), 1)
        self.assertEqual(after_e2[0].id, e3.id)

    def test_latest_cursor(self):
        """Get latest event ID for reconnection."""
        _reset_for_testing()

        e1 = publish_event('event1', {})
        cursor1 = get_latest_cursor()
        self.assertEqual(cursor1, e1.id)

        e2 = publish_event('event2', {})
        cursor2 = get_latest_cursor()
        self.assertEqual(cursor2, e2.id)


class EventAPIEndpointTest(TestCase):
    """Test /api/whatsapp/events/stream/ endpoint."""

    @classmethod
    def setUpTestData(cls):
        """Create test user."""
        cls.user = User.objects.create_user('testuser', 'test@test.com', 'pass123')

    def setUp(self):
        """Reset event bus and authenticate."""
        _reset_for_testing()
        self.client = Client()
        self.client.login(username='testuser', password='pass123')

    def test_endpoint_requires_login(self):
        """Endpoint should require authentication."""
        client = Client()
        response = client.get(reverse('api-events-stream'))

        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_endpoint_returns_events(self):
        """Endpoint should return events in JSON."""
        # Publish event
        event = publish_event('test', {'msg': 'hello'})

        response = self.client.get(reverse('api-events-stream'))

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn('events', data)
        self.assertIn('latest_cursor', data)
        self.assertIn('timestamp', data)

        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['events'][0]['type'], 'test')
        self.assertEqual(data['latest_cursor'], event.id)

    def test_endpoint_respects_cursor(self):
        """Endpoint should filter by cursor param."""
        e1 = publish_event('event1', {})
        e2 = publish_event('event2', {})

        # Without cursor: get all
        response = self.client.get(reverse('api-events-stream'))
        data = response.json()
        self.assertEqual(len(data['events']), 2)

        # With cursor=e1.id: get only e2
        response = self.client.get(reverse('api-events-stream'), {'cursor': e1.id})
        data = response.json()
        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['events'][0]['id'], e2.id)

    def test_endpoint_invalid_cursor(self):
        """Invalid cursor should default to 0."""
        e1 = publish_event('event1', {})

        response = self.client.get(
            reverse('api-events-stream'),
            {'cursor': 'invalid'}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['events']), 1)


class EventSignalsTest(TestCase):
    """Test signals that publish events."""

    def setUp(self):
        """Reset event bus before each test."""
        _reset_for_testing()

    def test_conversation_created_publishes_event(self):
        """Creating conversation should publish event."""
        cliente = Cliente.objects.create(
            nombre='Test Cliente',
            telefono='+5199999999'
        )
        channel = WhatsAppChannel.objects.create(
            nombre='Test Channel',
            phone_number_id='test_ch',
            numero_visible='+5199999999',
            activo=True
        )

        # Create conversation
        conv = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=channel
        )

        # Check events
        events = get_events(cursor=0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, 'conversation_created')
        self.assertEqual(events[0].data['conversation_id'], conv.id)
