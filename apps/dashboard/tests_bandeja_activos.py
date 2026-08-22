"""Tests for active channel filtering in bandeja (FASE 5B)."""
from django.test import TestCase, RequestFactory, Client
from django.contrib.auth.models import User
from django.urls import reverse
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp
from apps.clientes.models import Cliente
from .views_whatsapp import _filtrar_conversaciones


class BandejaActiveChannelsTest(TestCase):
    """Test that bandeja only shows conversations from active channels."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user('testuser', 'test@test.com', 'pass')
        cls.cliente = Cliente.objects.create(nombre='Walter Client', telefono='+5199999999')

        # Active channels
        cls.channel_active_1 = WhatsAppChannel.objects.create(
            nombre='Lima Express',
            phone_number_id='+51967619238',
            numero_visible='+51967619238',
            activo=True
        )
        cls.channel_active_2 = WhatsAppChannel.objects.create(
            nombre='TEST Meta Stage',
            phone_number_id='1171095159415009',
            numero_visible='+1 (555) 661-2885',
            activo=True
        )

        # Inactive channels (seed)
        cls.channel_inactive_1 = WhatsAppChannel.objects.create(
            nombre='Taxi Carga (seed)',
            phone_number_id='seed_taxi_carga',
            numero_visible='51999000001',
            activo=False
        )
        cls.channel_inactive_2 = WhatsAppChannel.objects.create(
            nombre='Lima Express (seed)',
            phone_number_id='seed_lima_express',
            numero_visible='51999000002',
            activo=False
        )

        # Conversations on active channels
        cls.conv_active_1 = ConversacionWhatsApp.objects.create(
            cliente=cls.cliente,
            channel=cls.channel_active_1,
            resumen='Active conversation 1'
        )
        cls.conv_active_2 = ConversacionWhatsApp.objects.create(
            cliente=cls.cliente,
            channel=cls.channel_active_2,
            resumen='Active conversation 2'
        )

        # Conversations on inactive channels
        cls.conv_inactive_1 = ConversacionWhatsApp.objects.create(
            cliente=cls.cliente,
            channel=cls.channel_inactive_1,
            resumen='Inactive conversation 1'
        )
        cls.conv_inactive_2 = ConversacionWhatsApp.objects.create(
            cliente=cls.cliente,
            channel=cls.channel_inactive_2,
            resumen='Inactive conversation 2'
        )

    def test_active_channel_appears(self):
        """Conversation on active channel should appear in filtered results."""
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user

        qs = ConversacionWhatsApp.objects.all()
        # Direct check: conversations exist and channel is active
        self.assertEqual(qs.count(), 4)  # 2 active + 2 inactive
        self.assertTrue(qs.filter(channel__activo=True).exists())

        filtered = _filtrar_conversaciones(qs, request)
        filtered_list = list(filtered.values_list('id', flat=True))

        # Debug: print what we got
        print(f"\nTotal conversations: {qs.count()}")
        print(f"Conversations with active channel: {qs.filter(channel__activo=True).count()}")
        print(f"After filter function: {len(filtered_list)}")
        print(f"Expected conv_active_1: {self.conv_active_1.id}")

        self.assertIn(self.conv_active_1.id, filtered_list)

    def test_inactive_channel_excluded(self):
        """Conversation on inactive channel should NOT appear in filtered results."""
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user

        qs = ConversacionWhatsApp.objects.all()
        filtered = _filtrar_conversaciones(qs, request)

        self.assertNotIn(self.conv_inactive_1.id, list(filtered.values_list('id', flat=True)))
        self.assertNotIn(self.conv_inactive_2.id, list(filtered.values_list('id', flat=True)))

    def test_multiple_active_channels(self):
        """All active channel conversations should appear."""
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user

        qs = ConversacionWhatsApp.objects.all()
        filtered = _filtrar_conversaciones(qs, request)

        filtered_ids = list(filtered.values_list('id', flat=True))
        self.assertIn(self.conv_active_1.id, filtered_ids)
        self.assertIn(self.conv_active_2.id, filtered_ids)

    def test_count_excludes_inactive(self):
        """Total count should exclude inactive channel conversations."""
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user

        qs = ConversacionWhatsApp.objects.all()
        filtered = _filtrar_conversaciones(qs, request)

        # Should only have 2 conversations (active only)
        self.assertEqual(filtered.count(), 2)

    def test_inactive_conversation_still_exists(self):
        """Inactive channel conversation should still exist in database."""
        # Verify data is not deleted, just filtered
        self.assertTrue(ConversacionWhatsApp.objects.filter(
            id=self.conv_inactive_1.id
        ).exists())

    def test_channel_filter_param_still_works(self):
        """Manual channel filter via GET param should still work."""
        factory = RequestFactory()
        request = factory.get('/?channel=1')  # Request specific channel
        request.user = self.user

        qs = ConversacionWhatsApp.objects.all()
        filtered = _filtrar_conversaciones(qs, request)

        # Should filter to that specific active channel
        filtered_ids = list(filtered.values_list('id', flat=True))
        # Only conversations from channel_active_1 should appear
        for conv in filtered:
            self.assertEqual(conv.channel_id, self.channel_active_1.id)

    def test_pagination_respects_active_filter(self):
        """Pagination should apply after active channel filter."""
        factory = RequestFactory()
        request = factory.get('/?limit=1')
        request.user = self.user

        qs = ConversacionWhatsApp.objects.all()
        filtered = _filtrar_conversaciones(qs, request)

        # Count should still be 2 (active only), not 4
        self.assertEqual(filtered.count(), 2)

    def test_search_respects_active_filter(self):
        """Search should not show results from inactive channels."""
        factory = RequestFactory()
        request = factory.get('/?q=Inactive')
        request.user = self.user

        qs = ConversacionWhatsApp.objects.all()
        filtered = _filtrar_conversaciones(qs, request)

        # Should find 0 results even though matching text exists
        self.assertEqual(filtered.count(), 0)


class BandejaAPIActiveChannelsTest(TestCase):
    """Test that queryset-level filtering respects active channels in API layer."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user('apiuser', 'api@test.com', 'pass123')

        cls.cliente = Cliente.objects.create(nombre='Walter Production Client', telefono='+5199999999')

        # Active channel
        cls.channel_active = WhatsAppChannel.objects.create(
            nombre='Production Channel',
            phone_number_id='prod_1234567890',
            numero_visible='+51967619238',
            activo=True
        )

        # Inactive channel
        cls.channel_inactive = WhatsAppChannel.objects.create(
            nombre='Seed Channel',
            phone_number_id='seed_old',
            numero_visible='51999000001',
            activo=False
        )

        # Create conversations
        cls.conv_active = ConversacionWhatsApp.objects.create(
            cliente=cls.cliente,
            channel=cls.channel_active,
            resumen='Production conversation'
        )

        cls.conv_inactive = ConversacionWhatsApp.objects.create(
            cliente=cls.cliente,
            channel=cls.channel_inactive,
            resumen='Seed conversation'
        )

    def test_queryset_filter_respects_active_channels(self):
        """Verify that queryset-level filtering works as expected by API."""
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user

        # Simulate what API endpoint does
        qs = ConversacionWhatsApp.objects.select_related(
            "cliente", "lead", "channel", "responsable"
        )
        filtered = _filtrar_conversaciones(qs, request)

        # Should only have the active conversation
        filtered_ids = list(filtered.values_list('id', flat=True))
        self.assertIn(self.conv_active.id, filtered_ids)
        self.assertNotIn(self.conv_inactive.id, filtered_ids)

    def test_filter_includes_only_active_channels(self):
        """Filter function must include only active channel conversations."""
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user

        # Before filter: 2 conversations
        all_convs = ConversacionWhatsApp.objects.all()
        self.assertEqual(all_convs.count(), 2)

        # After filter: 1 conversation (active only)
        filtered = _filtrar_conversaciones(all_convs, request)
        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first().id, self.conv_active.id)
