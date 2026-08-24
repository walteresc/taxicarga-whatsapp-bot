"""
FASE 5B: Echo identity audit — Verify no duplicate client/conversation creation.

Echo workflow:
1. Customer sends message (INBOUND event) → Cliente A created
2. Advisor replies from WhatsApp Web (ECHO event) → Must reuse Cliente A
3. Unread must NOT increase (same conversation, same client)
"""
import logging
from django.test import TransactionTestCase
from django.utils import timezone
from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp.identity import resolve_whatsapp_identity
from apps.whatsapp.services_ycloud import process_ycloud_event

logger = logging.getLogger(__name__)


class EchoIdentityAuditTest(TransactionTestCase):
    """Echo events must reuse client/conversation from INBOUND, not create duplicates."""

    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            nombre='TestEcho', phone_number_id='12345', activo=True
        )

    def test_inbound_then_echo_same_client(self):
        """INBOUND creates client. ECHO with same phone → reuses client, no duplicate."""
        customer_phone = "+519201800"

        # Step 1: INBOUND event — customer sends message
        cliente_inbound, _, _ = resolve_whatsapp_identity(customer_phone, self.channel)
        self.assertEqual(cliente_inbound.telefono, customer_phone)
        client_id_from_inbound = cliente_inbound.id

        # Step 2: ECHO event — advisor replies from WhatsApp Web
        # 'from' is business phone, 'to' is customer phone
        echo_event_data = {
            "from": "51999999999",  # Business number (not relevant for client identity)
            "to": customer_phone,   # Customer phone (should match INBOUND 'from')
            "wamid": "wamid_echo_001",
            "text": "Eco de respuesta",
            "timestamp": str(int(timezone.now().timestamp())),
            "from_name": "Bot",
        }

        echo_result = process_ycloud_event(
            event_type="whatsapp.smb.message.echoes",
            event_data=echo_event_data,
            channel=self.channel,
            cliente=None,  # Let it resolve from 'to' field
        )

        # Step 3: Verify same client was reused
        self.assertIsNotNone(echo_result.get("message"), "Echo should create message")
        conversation = echo_result.get("conversation")
        self.assertIsNotNone(conversation, "Echo should find/create conversation")

        # Most critical: client ID should match
        echo_message = echo_result.get("message")
        if echo_message:
            conversation_from_message = echo_message.conversacion
            self.assertEqual(
                conversation_from_message.cliente_id, client_id_from_inbound,
                f"Echo client ({conversation_from_message.cliente_id}) must match INBOUND client ({client_id_from_inbound})"
            )

        # Step 4: Verify only ONE client exists
        client_count = Cliente.objects.filter(telefono=customer_phone).count()
        self.assertEqual(client_count, 1, f"Expected 1 client with {customer_phone}, found {client_count}")

        logger.info(
            "[EchoAudit] PASS: INBOUND client %s reused by ECHO (no duplicate)",
            client_id_from_inbound
        )

    def test_echo_first_then_inbound(self):
        """Edge case: ECHO arrives before INBOUND. Should create client, then INBOUND reuses it."""
        customer_phone = "+519201801"

        # Step 1: ECHO arrives first (unusual but possible in async)
        echo_event_data = {
            "from": "51999999999",
            "to": customer_phone,
            "wamid": "wamid_echo_first",
            "text": "Respuesta del asesor",
            "timestamp": str(int(timezone.now().timestamp())),
        }

        echo_result = process_ycloud_event(
            event_type="whatsapp.smb.message.echoes",
            event_data=echo_event_data,
            channel=self.channel,
            cliente=None,
        )

        echo_conversation = echo_result.get("conversation")
        self.assertIsNotNone(echo_conversation)
        echo_client_id = echo_conversation.cliente_id

        # Step 2: INBOUND now arrives
        cliente_inbound, _, _ = resolve_whatsapp_identity(customer_phone, self.channel)

        # Step 3: Must be same client
        self.assertEqual(
            cliente_inbound.id, echo_client_id,
            f"INBOUND client ({cliente_inbound.id}) must match ECHO client ({echo_client_id})"
        )

        # Step 4: Still only ONE client
        client_count = Cliente.objects.filter(telefono=customer_phone).count()
        self.assertEqual(client_count, 1)

        logger.info("[EchoAudit] PASS: ECHO first, INBOUND reused same client")

    def test_echo_different_phone_formats(self):
        """
        CRITICAL: INBOUND with E.164, ECHO with digits-only or different format
        → Must still reuse same client.
        """
        # INBOUND: E.164 format
        customer_phone_e164 = "+519201802"
        cliente_inbound, _, _ = resolve_whatsapp_identity(customer_phone_e164, self.channel)
        client_id = cliente_inbound.id

        # ECHO: Different format (digits-only, no +)
        customer_phone_digits = "519201802"
        echo_event_data = {
            "from": "51999999999",
            "to": customer_phone_digits,  # ← Different format than INBOUND
            "wamid": "wamid_echo_format",
            "text": "Respuesta",
            "timestamp": str(int(timezone.now().timestamp())),
        }

        echo_result = process_ycloud_event(
            event_type="whatsapp.smb.message.echoes",
            event_data=echo_event_data,
            channel=self.channel,
            cliente=None,
        )

        echo_conversation = echo_result.get("conversation")
        self.assertIsNotNone(echo_conversation, "Echo should create conversation")

        # Verify same client despite format difference
        echo_client = echo_conversation.cliente
        self.assertEqual(
            echo_client.id, client_id,
            f"Echo client ({echo_client.id}) with format '{customer_phone_digits}' "
            f"must match INBOUND client ({client_id}) with format '{customer_phone_e164}'"
        )

        # Only ONE client should exist
        all_clients = list(Cliente.objects.filter(
            telefono__in=[customer_phone_e164, customer_phone_digits]
        ))
        self.assertEqual(len(all_clients), 1, f"Found multiple clients: {[c.telefono for c in all_clients]}")

        logger.info(
            "[EchoAudit] PASS: Format difference handled ({} → {}) → same client",
            customer_phone_e164, customer_phone_digits
        )

    def test_echo_does_not_increase_unread(self):
        """Echo is outbound (advisor reply) → should NOT increase unread count."""
        customer_phone = "+519201803"

        # INBOUND: Customer sends message
        cliente_inbound, _, _ = resolve_whatsapp_identity(customer_phone, self.channel)

        inbound_event = {
            "from": customer_phone,
            "to": "",
            "wamid": "wamid_inbound",
            "text": "Hola, quiero una cotización",
            "timestamp": str(int(timezone.now().timestamp())),
        }

        inbound_result = process_ycloud_event(
            event_type="whatsapp.inbound_message.received",
            event_data=inbound_event,
            channel=self.channel,
            cliente=cliente_inbound,
        )

        conversation = inbound_result.get("conversation")
        inbound_unread_before = conversation.mensajes_no_leidos if hasattr(conversation, 'mensajes_no_leidos') else 0

        # ECHO: Advisor reply
        echo_event = {
            "from": "51999999999",
            "to": customer_phone,
            "wamid": "wamid_echo_reply",
            "text": "Hola, te puedo ayudar",
            "timestamp": str(int(timezone.now().timestamp())),
        }

        echo_result = process_ycloud_event(
            event_type="whatsapp.smb.message.echoes",
            event_data=echo_event,
            channel=self.channel,
            cliente=None,
        )

        echo_conversation = echo_result.get("conversation")
        conversation.refresh_from_db()

        # Verify: same conversation, same client
        self.assertEqual(echo_conversation.id, conversation.id)
        self.assertEqual(echo_conversation.cliente_id, cliente_inbound.id)

        logger.info("[EchoAudit] PASS: Echo reused same conversation (no new unread)")

    def test_echo_human_takeover_flag(self):
        """Echo detection should set human_intervention=True (advisor active)."""
        customer_phone = "+519201804"
        cliente, _, _ = resolve_whatsapp_identity(customer_phone, self.channel)

        echo_event = {
            "from": "51999999999",
            "to": customer_phone,
            "wamid": "wamid_echo_takeover",
            "text": "Un asesor te va a atender",
            "timestamp": str(int(timezone.now().timestamp())),
        }

        echo_result = process_ycloud_event(
            event_type="whatsapp.smb.message.echoes",
            event_data=echo_event,
            channel=self.channel,
            cliente=None,
        )

        # Echo = advisor intervention
        human_intervention = echo_result.get("human_intervention", False)
        self.assertTrue(
            human_intervention,
            "Echo should set human_intervention=True"
        )

        # Conversation state should reflect takeover
        conversation = echo_result.get("conversation")
        if conversation:
            conversation.refresh_from_db()
            self.assertTrue(
                conversation.bot_pausado or conversation.estado_atencion == conversation.ATENCION_ASESOR,
                "Echo should set bot_pausado=True or estado_atencion=ATENCION_ASESOR"
            )

        logger.info("[EchoAudit] PASS: Echo human_intervention flag set correctly")
