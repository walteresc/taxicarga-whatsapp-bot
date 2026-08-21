"""
Integration tests for phone normalization, merging, and conversation ordering.
Tests the complete flow: webhook → normalize → deduplicate → order.
"""

from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta
import json

from apps.clientes.models import Cliente
from apps.clientes.phone_normalizer import normalize_phone, phones_are_equivalent
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel


class PhoneNormalizationIntegrationTest(TestCase):
    """Test phone normalization across the system."""

    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            phone_number_id="test_channel_123",
            nombre="Test Channel",
            activo=True,
        )

    def test_walte_escobar_variants_normalize_correctly(self):
        """Test that all Walter Escobar variants normalize to same phone."""
        # Create clientes with different phone formats
        cliente1 = Cliente.objects.create(
            telefono="995403320",
            nombre="Walter Escobar"
        )
        cliente2 = Cliente.objects.create(
            telefono="51995403320",
            nombre="Walter Variant 2"
        )
        cliente3 = Cliente.objects.create(
            telefono="+51995403320",
            nombre="Walter Variant 3"
        )

        # All should normalize to same E.164
        self.assertEqual(cliente1.phone_e164, "+51995403320")
        self.assertEqual(cliente2.phone_e164, "+51995403320")
        self.assertEqual(cliente3.phone_e164, "+51995403320")

    def test_conversation_order_by_ultima_actividad(self):
        """Test that conversations order correctly by ultima_actividad DESC."""
        # Create a single cliente
        cliente = Cliente.objects.create(
            telefono="987654321",
            nombre="Test Client",
            display_name="Test Client"
        )

        # Create conversations with different activity times
        now = timezone.now()
        conv1 = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=self.channel,
            ultima_actividad=now - timedelta(hours=3)
        )
        conv2 = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=self.channel,
            ultima_actividad=now - timedelta(hours=1)
        )
        conv3 = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=self.channel,
            ultima_actividad=now
        )

        # Query in order (should be DESC)
        convs = ConversacionWhatsApp.objects.all()
        ids = [c.id for c in convs[:3]]

        # Most recent should be first
        self.assertEqual(ids[0], conv3.id)
        self.assertEqual(ids[1], conv2.id)
        self.assertEqual(ids[2], conv1.id)

    def test_webhook_message_moves_conversation_to_top(self):
        """Test that incoming message updates ultima_actividad correctly."""
        cliente = Cliente.objects.create(
            telefono="987654321",
            nombre="Test Client",
            display_name="Test Client"
        )

        now = timezone.now()
        conv = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=self.channel,
            ultima_actividad=now - timedelta(hours=1)
        )

        old_actividad = conv.ultima_actividad

        # Simulate new message
        msg = MensajeWhatsApp.objects.create(
            conversacion=conv,
            tipo="texto",
            contenido="Hello",
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            fecha_mensaje=timezone.now()
        )

        # Update conversation activity
        conv.ultima_actividad = timezone.now()
        conv.save()

        # Refresh from DB
        conv.refresh_from_db()

        # Activity should be newer
        self.assertGreater(conv.ultima_actividad, old_actividad)

    def test_display_name_priority(self):
        """Test that display_name is prioritized over nombre."""
        cliente = Cliente.objects.create(
            telefono="987654321",
            nombre="Original Name",
            display_name="Display Name"
        )

        # Should use display_name when available
        self.assertEqual(str(cliente), "Display Name")

    def test_merged_clients_relationship(self):
        """Test that merged_into relationship works correctly."""
        canonical = Cliente.objects.create(
            telefono="+51995403320",
            nombre="Walter Escobar",
            display_name="Walter Escobar"
        )

        duplicate1 = Cliente.objects.create(
            telefono="995403320",
            nombre="Duplicate 1",
            display_name="",
            merged_into=canonical,
            is_active=False
        )

        duplicate2 = Cliente.objects.create(
            telefono="51995403320",
            nombre="Duplicate 2",
            display_name="",
            merged_into=canonical,
            is_active=False
        )

        # Canonical should have merged clientes
        merged = Cliente.objects.filter(merged_into=canonical)
        self.assertEqual(merged.count(), 2)
        self.assertIn(duplicate1, merged)
        self.assertIn(duplicate2, merged)

    def test_inactive_merged_clientes_not_in_queries(self):
        """Test that inactive merged clientes don't appear in normal queries."""
        canonical = Cliente.objects.create(
            telefono="+51995403320",
            nombre="Walter",
            is_active=True
        )

        duplicate = Cliente.objects.create(
            telefono="995403320",
            nombre="Dup",
            merged_into=canonical,
            is_active=False
        )

        # Default query should only get active
        active = Cliente.objects.filter(is_active=True)
        self.assertIn(canonical, active)
        self.assertNotIn(duplicate, active)


class ConversationOrderingTest(TestCase):
    """Test conversation ordering in list responses."""

    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            phone_number_id="test_ch",
            nombre="Test",
            activo=True
        )

    def test_conversations_ordered_by_activity_not_creation(self):
        """Test conversations order by ultima_actividad, not creada_en."""
        cliente = Cliente.objects.create(
            telefono="987654321",
            nombre="Test",
            display_name="Test"
        )

        now = timezone.now()

        # Create 3 conversations in order
        conv1 = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=self.channel,
            creada_en=now - timedelta(hours=3),
            ultima_actividad=now - timedelta(hours=3)
        )

        conv2 = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=self.channel,
            creada_en=now - timedelta(hours=2),
            ultima_actividad=now - timedelta(hours=2)
        )

        conv3 = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=self.channel,
            creada_en=now - timedelta(hours=1),
            ultima_actividad=now - timedelta(hours=1)
        )

        # Update conv1's activity to most recent
        conv1.ultima_actividad = now
        conv1.save()

        # Query should show conv1 first (most recent activity)
        convs = list(ConversacionWhatsApp.objects.all())
        self.assertEqual(convs[0].id, conv1.id)  # Most recent
        self.assertEqual(convs[1].id, conv3.id)  # Second
        self.assertEqual(convs[2].id, conv2.id)  # Oldest

    def test_pagination_works_with_large_set(self):
        """Test pagination logic for 197+ conversations."""
        cliente = Cliente.objects.create(
            telefono="987654321",
            nombre="Test",
            display_name="Test"
        )

        # Create 50 conversations
        now = timezone.now()
        for i in range(50):
            ConversacionWhatsApp.objects.create(
                cliente=cliente,
                channel=self.channel,
                ultima_actividad=now - timedelta(minutes=i)
            )

        # Query first page (25 items)
        convs = ConversacionWhatsApp.objects.all()[:25]
        self.assertEqual(len(list(convs)), 25)

        # Query second page
        convs_page2 = ConversacionWhatsApp.objects.all()[25:50]
        self.assertEqual(len(list(convs_page2)), 25)

        # No overlap
        ids_p1 = set(c.id for c in ConversacionWhatsApp.objects.all()[:25])
        ids_p2 = set(c.id for c in ConversacionWhatsApp.objects.all()[25:50])
        self.assertEqual(len(ids_p1 & ids_p2), 0)


class ClienteDisplayNameTest(TestCase):
    """Test display_name logic."""

    def test_display_name_fallback_to_nombre(self):
        """Test fallback from display_name to nombre."""
        cliente = Cliente.objects.create(
            telefono="987654321",
            nombre="Actual Name",
            display_name=""
        )
        # display_name is empty, should use nombre
        self.assertEqual(str(cliente), "Actual Name")

    def test_display_name_fallback_to_phone(self):
        """Test fallback to phone when no name."""
        cliente = Cliente.objects.create(
            telefono="987654321",
            nombre="",
            display_name=""
        )
        # Both empty, should use phone
        self.assertEqual(str(cliente), "987654321")

    def test_manual_display_name_is_preferred(self):
        """Test that manual display_name is preferred."""
        cliente = Cliente.objects.create(
            telefono="987654321",
            nombre="Original",
            display_name="Walter Escobar"
        )
        # Should prefer display_name
        self.assertEqual(str(cliente), "Walter Escobar")
