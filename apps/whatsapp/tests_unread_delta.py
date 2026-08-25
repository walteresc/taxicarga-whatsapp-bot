"""
Tests for unread_delta in message.created events.
Validates that backend publishes correct delta values, not global totals.
"""
import json
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.whatsapp.redis_events import get_event_bus
from unittest.mock import patch, MagicMock

User = get_user_model()


class UnreadDeltaSignalTests(TestCase):
    """Test unread_delta publication in message.created events."""

    def setUp(self):
        """Create test fixtures."""
        self.channel = WhatsAppChannel.objects.create(
            numero_visible="+51967619238",
            nombre="Test Channel",
            activo=True,
        )

        self.cliente = Cliente.objects.create(
            telefono="+51995403320",
            nombre="Test Cliente",
        )

        self.conv = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            channel=self.channel,
        )

    @patch('apps.whatsapp.signals.publish_event')
    def test_inbound_message_publishes_unread_delta_1(self, mock_publish):
        """Inbound message from customer should publish unread_delta=1."""
        mock_publish.return_value = MagicMock(id='test-event-1')

        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id='wamid-test-001',
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.CLIENTE,
            contenido="Test inbound message",
            sender_type='customer',
        )

        # Verify publish_event was called
        mock_publish.assert_called_once()
        event_type, event_data = mock_publish.call_args[0]

        self.assertEqual(event_type, 'message.created')
        self.assertEqual(event_data['conversation']['unread_delta'], 1)
        self.assertEqual(event_data['sender_type'], 'customer')

    @patch('apps.whatsapp.signals.publish_event')
    def test_advisor_message_publishes_unread_delta_0(self, mock_publish):
        """Advisor outbound message should publish unread_delta=0."""
        mock_publish.return_value = MagicMock(id='test-event-2')

        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id='wamid-test-002',
            direccion=MensajeWhatsApp.SALIENTE,
            origen=MensajeWhatsApp.ASESOR,
            contenido="Test advisor response",
            sender_type='advisor',
        )

        mock_publish.assert_called_once()
        event_type, event_data = mock_publish.call_args[0]

        self.assertEqual(event_type, 'message.created')
        self.assertEqual(event_data['conversation']['unread_delta'], 0)

    @patch('apps.whatsapp.signals.publish_event')
    def test_echo_message_publishes_unread_delta_0(self, mock_publish):
        """Echo/bot inbound message should publish unread_delta=0."""
        mock_publish.return_value = MagicMock(id='test-event-3')

        # Echo is inbound (ENTRANTE) but from bot/system
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id='wamid-test-echo-001',
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.BOT,  # Or SISTEMA
            contenido="Echo response",
            sender_type='bot',
        )

        mock_publish.assert_called_once()
        event_type, event_data = mock_publish.call_args[0]

        self.assertEqual(event_type, 'message.created')
        # Only customer inbound = delta 1. Echo is not counted
        self.assertEqual(event_data['conversation']['unread_delta'], 0)

    @patch('apps.whatsapp.signals.publish_event')
    def test_event_contains_no_global_unread_total(self, mock_publish):
        """Event should NOT publish a global unread_count total."""
        mock_publish.return_value = MagicMock(id='test-event-4')

        # Create a message when there are already "unread" msgs
        # (doesn't matter - we don't publish total)
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id='wamid-test-005',
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.CLIENTE,
            contenido="Another message",
            sender_type='customer',
        )

        mock_publish.assert_called_once()
        event_type, event_data = mock_publish.call_args[0]

        # The event should have unread_delta (incremental), NOT unread_count (absolute)
        self.assertIn('unread_delta', event_data['conversation'])
        # Should NOT have 'total_unread' or similar field
        self.assertNotIn('total_unread', event_data['conversation'])

    @patch('apps.whatsapp.signals.publish_event')
    def test_multiple_inbound_messages_each_publish_delta_1(self, mock_publish):
        """Multiple inbound messages should each publish delta=1, independently."""
        mock_publish.return_value = MagicMock(id='test-event-multiple')

        # Message 1
        MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id='wamid-test-100',
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.CLIENTE,
            contenido="First message",
            sender_type='customer',
        )

        self.assertEqual(mock_publish.call_count, 1)
        event1_data = mock_publish.call_args_list[0][0][1]
        self.assertEqual(event1_data['conversation']['unread_delta'], 1)

        # Message 2
        mock_publish.reset_mock()
        mock_publish.return_value = MagicMock(id='test-event-second')

        MensajeWhatsApp.objects.create(
            conversacion=self.conv,
            meta_message_id='wamid-test-101',
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.CLIENTE,
            contenido="Second message",
            sender_type='customer',
        )

        self.assertEqual(mock_publish.call_count, 1)
        event2_data = mock_publish.call_args[0][1]
        self.assertEqual(event2_data['conversation']['unread_delta'], 1)
