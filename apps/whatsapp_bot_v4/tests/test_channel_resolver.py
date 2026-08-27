"""Test channel resolver from YCloud webhook payloads."""
import json
from django.test import TestCase
from apps.whatsapp.models import WhatsAppChannel
from apps.whatsapp_bot_v4.services.ycloud_webhook_service import (
    _normalize_phone_number,
    _resolve_channel_from_payload,
)


class PhoneNormalizationTest(TestCase):
    """Test phone number normalization to E.164 without +"""

    def test_normalize_with_plus_and_spaces(self):
        result = _normalize_phone_number('+51 967 619 238')
        self.assertEqual(result, '51967619238')

    def test_normalize_with_plus_only(self):
        result = _normalize_phone_number('+51967619238')
        self.assertEqual(result, '51967619238')

    def test_normalize_without_plus(self):
        result = _normalize_phone_number('51967619238')
        self.assertEqual(result, '51967619238')

    def test_normalize_with_hyphens(self):
        result = _normalize_phone_number('51-967-619-238')
        self.assertEqual(result, '51967619238')

    def test_normalize_with_parens(self):
        result = _normalize_phone_number('+51 (967) 619-238')
        self.assertEqual(result, '51967619238')

    def test_normalize_none_input(self):
        result = _normalize_phone_number(None)
        self.assertIsNone(result)

    def test_normalize_empty_string(self):
        result = _normalize_phone_number('')
        self.assertIsNone(result)

    def test_normalize_non_numeric(self):
        result = _normalize_phone_number('abc')
        self.assertIsNone(result)


class ChannelResolverTest(TestCase):
    """Test channel resolution from YCloud webhook event payloads."""

    @classmethod
    def setUpTestData(cls):
        """Create test channels."""
        # Lima Express (active)
        cls.lima_express = WhatsAppChannel.objects.create(
            nombre='Lima Express',
            phone_number_id='+51967619238',
            numero_visible='+51967619238',
            activo=True
        )

        # Taxi Carga (active, test only)
        cls.taxi_carga = WhatsAppChannel.objects.create(
            nombre='Taxi Carga',
            phone_number_id='+51952871071',
            numero_visible='952871071',
            activo=True
        )

        # Inactive channel
        cls.inactive = WhatsAppChannel.objects.create(
            nombre='Inactive Channel',
            phone_number_id='55999000000',
            numero_visible='55999000000',
            activo=False
        )

    def test_inbound_with_plus_e164(self):
        """Inbound message to +51967619238"""
        canonical = {'to': '+51967619238'}
        payload = {}
        channel = _resolve_channel_from_payload(
            'whatsapp.inbound_message.received',
            canonical,
            payload
        )
        self.assertEqual(channel.id, self.lima_express.id)

    def test_inbound_without_plus(self):
        """Inbound message to 51967619238"""
        canonical = {'to': '51967619238'}
        payload = {}
        channel = _resolve_channel_from_payload(
            'whatsapp.inbound_message.received',
            canonical,
            payload
        )
        self.assertEqual(channel.id, self.lima_express.id)

    def test_inbound_with_spaces(self):
        """Inbound message to +51 967 619 238"""
        canonical = {'to': '+51 967 619 238'}
        payload = {}
        channel = _resolve_channel_from_payload(
            'whatsapp.inbound_message.received',
            canonical,
            payload
        )
        self.assertEqual(channel.id, self.lima_express.id)

    def test_inbound_fallback_to_raw_payload(self):
        """Canonical empty, extract from raw payload"""
        canonical = {}
        payload = {
            'whatsappInboundMessage': {'to': '+51967619238'}
        }
        channel = _resolve_channel_from_payload(
            'whatsapp.inbound_message.received',
            canonical,
            payload
        )
        self.assertEqual(channel.id, self.lima_express.id)

    def test_echo_with_plus_e164(self):
        """Echo message from +51967619238"""
        canonical = {'from': '+51967619238'}
        payload = {}
        channel = _resolve_channel_from_payload(
            'whatsapp.smb.message.echoes',
            canonical,
            payload
        )
        self.assertEqual(channel.id, self.lima_express.id)

    def test_echo_without_plus(self):
        """Echo message from 51967619238"""
        canonical = {'from': '51967619238'}
        payload = {}
        channel = _resolve_channel_from_payload(
            'whatsapp.smb.message.echoes',
            canonical,
            payload
        )
        self.assertEqual(channel.id, self.lima_express.id)

    def test_echo_fallback_to_raw_payload(self):
        """Echo: canonical empty, extract from raw payload"""
        canonical = {}
        payload = {
            'whatsappMessage': {'from': '+51967619238'}
        }
        channel = _resolve_channel_from_payload(
            'whatsapp.smb.message.echoes',
            canonical,
            payload
        )
        self.assertEqual(channel.id, self.lima_express.id)

    def test_unknown_number_returns_none(self):
        """Unknown business number returns None"""
        canonical = {'to': '+55999000001'}
        payload = {}
        channel = _resolve_channel_from_payload(
            'whatsapp.inbound_message.received',
            canonical,
            payload
        )
        self.assertIsNone(channel)

    def test_inactive_channel_skipped(self):
        """Inactive channel not returned even if number matches"""
        canonical = {'to': '55999000000'}
        payload = {}
        channel = _resolve_channel_from_payload(
            'whatsapp.inbound_message.received',
            canonical,
            payload
        )
        self.assertIsNone(channel)

    def test_taxi_carga_resolution(self):
        """Can also resolve Taxi Carga channel"""
        # Taxi Carga has numero_visible='952871071' (no +51)
        canonical = {'to': '+51952871071'}
        payload = {}
        channel = _resolve_channel_from_payload(
            'whatsapp.inbound_message.received',
            canonical,
            payload
        )
        self.assertEqual(channel.id, self.taxi_carga.id)

    def test_empty_payload_returns_none(self):
        """No business number in payload returns None"""
        canonical = {}
        payload = {}
        channel = _resolve_channel_from_payload(
            'whatsapp.inbound_message.received',
            canonical,
            payload
        )
        self.assertIsNone(channel)

    def test_status_update_no_to_from(self):
        """Status updates don't have 'to' or 'from' - should return None"""
        canonical = {}
        payload = {'id': 'wamid123', 'status': 'delivered'}
        channel = _resolve_channel_from_payload(
            'whatsapp.message.updated',
            canonical,
            payload
        )
        self.assertIsNone(channel)

    def test_same_client_different_channels(self):
        """Same cliente in different channels creates separate conversations"""
        # Both channels are active and can receive messages from same number
        # This is expected behavior - each channel has its own conversation
        canonical_lima = {'to': '+51967619238'}
        canonical_taxi = {'to': '+51952871071'}

        ch_lima = _resolve_channel_from_payload(
            'whatsapp.inbound_message.received',
            canonical_lima,
            {}
        )
        ch_taxi = _resolve_channel_from_payload(
            'whatsapp.inbound_message.received',
            canonical_taxi,
            {}
        )

        self.assertEqual(ch_lima.id, self.lima_express.id)
        self.assertEqual(ch_taxi.id, self.taxi_carga.id)
        self.assertNotEqual(ch_lima.id, ch_taxi.id)
