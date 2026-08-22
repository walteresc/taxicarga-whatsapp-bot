"""Tests for SSE and polling authorization (FASE 5B security)."""

from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp
from apps.whatsapp.redis_events import RedisEventBus


class SSEAuthorizationTest(TestCase):
    """Test SSE endpoint authorization."""

    @classmethod
    def setUpTestData(cls):
        """Create users and channels."""
        # Create groups
        cls.whatsapp_group = Group.objects.create(name='Asesor de Ventas')

        # Create users
        cls.authorized_user = User.objects.create_user(
            'authorized',
            'authorized@test.com',
            'pass123'
        )
        cls.authorized_user.groups.add(cls.whatsapp_group)

        cls.unauthorized_user = User.objects.create_user(
            'unauthorized',
            'unauthorized@test.com',
            'pass123'
        )

        # Create channels
        cls.active_channel = WhatsAppChannel.objects.create(
            nombre='Active Channel',
            phone_number_id='active_ch',
            numero_visible='+5199999999',
            activo=True
        )

        cls.inactive_channel = WhatsAppChannel.objects.create(
            nombre='Inactive Channel',
            phone_number_id='inactive_ch',
            numero_visible='+5199999998',
            activo=False
        )

    def setUp(self):
        """Clear Redis before each test."""
        try:
            bus = RedisEventBus()
            bus.clear()
        except Exception:
            self.skipTest("Redis not available")

    def test_unauthenticated_rejected(self):
        """Unauthenticated user should be rejected."""
        client = Client()
        response = client.get(reverse('sse-events-stream'))

        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_unauthorized_group_rejected(self):
        """User without WhatsApp group should be rejected."""
        client = Client()
        client.login(username='unauthorized', password='pass123')

        response = client.get(reverse('sse-events-stream'))

        # Should get 403 Forbidden
        self.assertEqual(response.status_code, 403)

    def test_authorized_accepted(self):
        """User in WhatsApp group should be accepted."""
        client = Client()
        client.login(username='authorized', password='pass123')

        response = client.get(reverse('sse-events-stream'), timeout=1)

        # Should get 200 (SSE stream)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/event-stream')

    def test_inactive_channel_not_transmitted(self):
        """Events from inactive channels should not be transmitted."""
        bus = RedisEventBus()

        # Publish event from inactive channel
        bus.publish('message.created', {
            'conversation_id': 1,
            'channel_id': self.inactive_channel.id,
            'message_id': 1,
            'sender_type': 'customer',
        })

        client = Client()
        client.login(username='authorized', password='pass123')

        # Try to poll
        response = client.get(
            reverse('api-events-poll'),
            {'cursor': '0'}
        )

        data = response.json()

        # No events should be returned (inactive channel filtered)
        self.assertEqual(len(data['events']), 0)

    def test_active_channel_transmitted(self):
        """Events from active channels should be transmitted."""
        bus = RedisEventBus()

        # Publish event from active channel
        bus.publish('message.created', {
            'conversation_id': 1,
            'channel_id': self.active_channel.id,
            'message_id': 1,
            'sender_type': 'customer',
        })

        client = Client()
        client.login(username='authorized', password='pass123')

        # Poll
        response = client.get(
            reverse('api-events-poll'),
            {'cursor': '0'}
        )

        data = response.json()

        # Event should be present
        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['events'][0]['data']['channel_id'], self.active_channel.id)

    def test_event_without_channel_not_transmitted(self):
        """Events without channel_id should not be transmitted."""
        bus = RedisEventBus()

        # Publish event without channel_id
        bus.publish('system.event', {
            'message': 'test',
        })

        client = Client()
        client.login(username='authorized', password='pass123')

        response = client.get(
            reverse('api-events-poll'),
            {'cursor': '0'}
        )

        data = response.json()

        # No events
        self.assertEqual(len(data['events']), 0)

    def test_polling_same_auth_as_sse(self):
        """Polling endpoint should use same authorization as SSE."""
        client = Client()

        # Unauthorized user should get 403
        client.login(username='unauthorized', password='pass123')

        response = client.get(reverse('api-events-poll'))
        self.assertEqual(response.status_code, 403)

        # Authorized user should get 200
        client.logout()
        client.login(username='authorized', password='pass123')

        response = client.get(reverse('api-events-poll'))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_access(self):
        """Superuser should have access."""
        superuser = User.objects.create_superuser(
            'admin',
            'admin@test.com',
            'pass123'
        )

        client = Client()
        client.login(username='admin', password='pass123')

        response = client.get(reverse('sse-events-stream'), timeout=1)
        self.assertEqual(response.status_code, 200)


class EventChannelFilteringTest(TestCase):
    """Test event filtering by channel."""

    @classmethod
    def setUpTestData(cls):
        """Create setup."""
        cls.whatsapp_group = Group.objects.create(name='Asesor de Ventas')
        cls.user = User.objects.create_user('user', 'user@test.com', 'pass123')
        cls.user.groups.add(cls.whatsapp_group)

        cls.ch1 = WhatsAppChannel.objects.create(
            nombre='Ch1',
            phone_number_id='ch1',
            numero_visible='+5199999991',
            activo=True
        )

        cls.ch2 = WhatsAppChannel.objects.create(
            nombre='Ch2',
            phone_number_id='ch2',
            numero_visible='+5199999992',
            activo=True
        )

        cls.ch3_inactive = WhatsAppChannel.objects.create(
            nombre='Ch3 Inactive',
            phone_number_id='ch3',
            numero_visible='+5199999993',
            activo=False
        )

    def setUp(self):
        """Clear Redis."""
        try:
            bus = RedisEventBus()
            bus.clear()
        except Exception:
            self.skipTest("Redis not available")

    def test_only_active_channels_in_authorized_list(self):
        """Only active channels should be in authorized set."""
        from apps.whatsapp.models import WhatsAppChannel

        active_ids = set(
            WhatsAppChannel.objects.filter(activo=True).values_list('id', flat=True)
        )

        self.assertIn(self.ch1.id, active_ids)
        self.assertIn(self.ch2.id, active_ids)
        self.assertNotIn(self.ch3_inactive.id, active_ids)

    def test_mixed_channels_filters_correctly(self):
        """Poll with mixed channels should filter correctly."""
        bus = RedisEventBus()

        # Publish events from all channels
        bus.publish('msg1', {'channel_id': self.ch1.id})
        bus.publish('msg2', {'channel_id': self.ch2.id})
        bus.publish('msg3', {'channel_id': self.ch3_inactive.id})

        client = Client()
        client.login(username='user', password='pass123')

        response = client.get(reverse('api-events-poll'), {'cursor': '0'})
        data = response.json()

        # Should only have 2 events (ch1, ch2)
        self.assertEqual(len(data['events']), 2)

        channel_ids = {e['data']['channel_id'] for e in data['events']}
        self.assertIn(self.ch1.id, channel_ids)
        self.assertIn(self.ch2.id, channel_ids)
        self.assertNotIn(self.ch3_inactive.id, channel_ids)
