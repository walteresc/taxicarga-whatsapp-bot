"""Integration tests for event streaming (PARTE B backend-to-API contract)."""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp
from apps.whatsapp.redis_events import RedisEventBus
from apps.whatsapp.test_factories import create_test_cliente, create_test_channel


class EventStreamingIntegrationTest(TestCase):
    """Test full event flow: model creation → signal → API response."""

    @classmethod
    def setUpTestData(cls):
        """Create test user and data."""
        cls.user = User.objects.create_user('testuser', 'test@test.com', 'pass123')

    def setUp(self):
        """Reset event bus and authenticate."""
        try:
            bus = RedisEventBus()
            bus.clear()
        except Exception:
            self.skipTest("Redis not available")
        self.client = Client()
        self.client.login(username='testuser', password='pass123')

    def test_conversation_creation_emits_event(self):
        """Creating conversation should emit event visible via API."""
        cliente = create_test_cliente('test_conversation_creation_emits_event')
        channel = create_test_channel()

        # Create conversation (triggers signal)
        conv = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=channel
        )

        # Poll API (cursor=0 means all events)
        response = self.client.get(
            reverse('api-events-stream'),
            {'cursor': 0}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should have event
        self.assertEqual(len(data['events']), 1)
        event = data['events'][0]
        self.assertEqual(event['type'], 'conversation_created')
        self.assertEqual(event['data']['conversation_id'], conv.id)

    def test_multiple_events_preserve_order(self):
        """Multiple events should maintain creation order."""
        cliente1 = create_test_cliente('test_multiple_events_preserve_order_1')
        cliente2 = create_test_cliente('test_multiple_events_preserve_order_2')
        channel = create_test_channel()

        # Create multiple conversations (different clients to avoid UNIQUE constraint)
        conv1 = ConversacionWhatsApp.objects.create(
            cliente=cliente1,
            channel=channel
        )
        conv2 = ConversacionWhatsApp.objects.create(
            cliente=cliente2,
            channel=channel
        )

        response = self.client.get(reverse('api-events-stream'))
        data = response.json()

        # Should have 2 events in order
        self.assertEqual(len(data['events']), 2)
        self.assertEqual(data['events'][0]['data']['conversation_id'], conv1.id)
        self.assertEqual(data['events'][1]['data']['conversation_id'], conv2.id)

    def test_cursor_pagination_works_end_to_end(self):
        """Client can use cursor to get only new events."""
        cliente1 = create_test_cliente('test_cursor_pagination_works_end_to_end_1')
        cliente2 = create_test_cliente('test_cursor_pagination_works_end_to_end_2')
        channel = create_test_channel()

        # Create first conversation
        conv1 = ConversacionWhatsApp.objects.create(
            cliente=cliente1,
            channel=channel
        )

        # Poll to get latest cursor
        response1 = self.client.get(reverse('api-events-stream'))
        data1 = response1.json()
        cursor = data1['latest_cursor']

        # Create second conversation (different client)
        conv2 = ConversacionWhatsApp.objects.create(
            cliente=cliente2,
            channel=channel
        )

        # Poll with cursor (should only get new events)
        response2 = self.client.get(
            reverse('api-events-stream'),
            {'cursor': cursor}
        )
        data2 = response2.json()

        # Should have only 1 new event
        self.assertEqual(len(data2['events']), 1)
        self.assertEqual(data2['events'][0]['data']['conversation_id'], conv2.id)

    def test_event_data_schema(self):
        """Verify event structure matches frontend expectations."""
        cliente = create_test_cliente('test_event_data_schema')
        channel = create_test_channel()

        conv = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=channel
        )

        response = self.client.get(reverse('api-events-stream'))
        data = response.json()
        event = data['events'][0]

        # Verify schema
        required_fields = ['id', 'type', 'timestamp', 'data']
        for field in required_fields:
            self.assertIn(field, event, f"Missing field: {field}")

        # Verify data content
        self.assertEqual(event['data']['conversation_id'], conv.id)
        self.assertEqual(event['data']['cliente_id'], cliente.id)
        self.assertEqual(event['data']['channel_id'], channel.id)
