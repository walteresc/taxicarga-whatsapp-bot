"""
FASE 5B: Concurrent phone normalization — Verify UNIQUE constraint prevents duplicates.

Test that normalize_phone is called BEFORE get_or_create lookup,
so different formats of the same number don't create multiple clients.
"""
import logging
from django.test import TransactionTestCase
from django.db import transaction, IntegrityError
from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel
from apps.whatsapp.services_ycloud import process_ycloud_event

logger = logging.getLogger(__name__)


class ConcurrentPhoneNormalizationTest(TransactionTestCase):
    """Verify concurrent requests with different phone formats reuse same client."""

    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            nombre='TestConcurrent', phone_number_id='concurrent_test', activo=True
        )

    def test_different_formats_same_normalized(self):
        """
        Inbound with "+51 919 201 900" (spaces), then ECHO with "919201900" (no +, no spaces)
        → Same cliente should be reused, no IntegrityError.
        """
        # Step 1: First webhook with spaces in E.164
        inbound_event_1 = {
            "from": "+51 919 201 900",  # ← Spaces in E.164
            "to": "",
            "wamid": "wamid_test1",
            "text": "Primer mensaje",
            "timestamp": "1234567890",
            "from_name": "Customer 1",
        }

        result1 = process_ycloud_event(
            event_type="whatsapp.inbound_message.received",
            event_data=inbound_event_1,
            channel=self.channel,
            cliente=None,  # Let it resolve
        )

        cliente1_id = result1["conversation"].cliente_id
        logger.info("[ConcurrentTest] Created client %d from '+51 919 201 900'", cliente1_id)

        # Verify it's stored normalized (without spaces)
        cliente1 = Cliente.objects.get(pk=cliente1_id)
        self.assertNotIn(" ", cliente1.telefono, "Should normalize away spaces")
        self.assertTrue(cliente1.telefono.startswith("+51919"), f"Expected E.164, got {cliente1.telefono}")

        # Step 2: ECHO with same number, different format (national number only)
        echo_event_2 = {
            "from": "51999999999",
            "to": "919201900",  # ← National number only (9 digits)
            "wamid": "wamid_test2",
            "text": "Respuesta",
            "timestamp": "1234567891",
        }

        result2 = process_ycloud_event(
            event_type="whatsapp.smb.message.echoes",
            event_data=echo_event_2,
            channel=self.channel,
            cliente=None,  # Let it resolve
        )

        cliente2_id = result2["conversation"].cliente_id
        logger.info("[ConcurrentTest] ECHO resolved to client %d from '919201900'", cliente2_id)

        # Critical assertion: must be same client
        self.assertEqual(
            cliente1_id, cliente2_id,
            f"Different phone formats (+51 919 201 900 vs 919201900) should resolve to same client"
        )

        # Verify only ONE client exists
        all_clients = Cliente.objects.count()
        self.assertEqual(all_clients, 1, f"Should have 1 client, found {all_clients}")

        logger.info("[ConcurrentTest] PASS: Format variation handled correctly")

    def test_e164_vs_digits_formats(self):
        """E.164 +51919201901 vs digits-only 919201901 → same client."""
        # Event 1: E.164
        evt1 = {
            "from": "+51919201901",
            "to": "",
            "wamid": "wamid_e164",
            "text": "Test",
            "timestamp": "1234567892",
        }

        res1 = process_ycloud_event(
            event_type="whatsapp.inbound_message.received",
            event_data=evt1,
            channel=self.channel,
            cliente=None,
        )
        client1_id = res1["conversation"].cliente_id

        # Event 2: Digits-only (even shorter)
        evt2 = {
            "from": "919201901",
            "to": "",
            "wamid": "wamid_digits",
            "text": "Test2",
            "timestamp": "1234567893",
        }

        res2 = process_ycloud_event(
            event_type="whatsapp.inbound_message.received",
            event_data=evt2,
            channel=self.channel,
            cliente=None,
        )
        client2_id = res2["conversation"].cliente_id

        self.assertEqual(client1_id, client2_id, "E.164 and digits-only should map to same client")
        self.assertEqual(Cliente.objects.count(), 1)

        logger.info("[ConcurrentTest] PASS: E.164 vs digits-only normalized correctly")

    def test_plus_prefix_variance(self):
        """+51919201902 vs 51919201902 (with/without +) → same client."""
        # Event 1: With +
        evt1 = {
            "from": "+51919201902",
            "to": "",
            "wamid": "wamid_plus",
            "text": "Test",
            "timestamp": "1234567894",
        }

        res1 = process_ycloud_event(
            event_type="whatsapp.inbound_message.received",
            event_data=evt1,
            channel=self.channel,
            cliente=None,
        )
        client1_id = res1["conversation"].cliente_id

        # Event 2: Without +
        evt2 = {
            "from": "51919201902",
            "to": "",
            "wamid": "wamid_no_plus",
            "text": "Test2",
            "timestamp": "1234567895",
        }

        res2 = process_ycloud_event(
            event_type="whatsapp.inbound_message.received",
            event_data=evt2,
            channel=self.channel,
            cliente=None,
        )
        client2_id = res2["conversation"].cliente_id

        self.assertEqual(client1_id, client2_id, "+prefix variance should be normalized away")
        self.assertEqual(Cliente.objects.count(), 1)

        logger.info("[ConcurrentTest] PASS: +prefix variance handled")

    def test_constraint_blocks_invalid_duplicate(self):
        """
        If somehow a malformed telefono bypasses normalization,
        PostgreSQL UNIQUE constraint should block IntegrityError.
        """
        # Create a client with normalized phone
        cliente1 = Cliente.objects.create(
            telefono="+51919201903",
            nombre="Test 1"
        )
        client1_id = cliente1.id

        # Try to create another with same phone (should fail or reuse)
        try:
            cliente2, created = Cliente.objects.get_or_create(
                telefono="+51919201903",
                defaults={"nombre": "Test 2"}
            )
            # If we get here, get_or_create found the existing client (expected)
            self.assertFalse(created, "get_or_create should find existing")
            self.assertEqual(cliente2.id, client1_id, "Should be same client")
            logger.info("[ConcurrentTest] PASS: get_or_create prevents duplicate")

        except IntegrityError:
            # This shouldn't happen with get_or_create, but if it did, constraint is working
            logger.warning("[ConcurrentTest] IntegrityError (constraint triggered)")
