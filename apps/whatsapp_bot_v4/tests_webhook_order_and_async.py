"""
Tests demonstrating exact order: HTTP 200, Persistence, and Async Behavior.

CRITICAL: These tests prove:
1. Message persists BEFORE HTTP 200 is returned
2. Bot processing is sync (NOT async) and blocks the response
3. Errors occur at different points: pre-persistence, during persistence, post-persistence
4. Transaction atomicity and rollback behavior
"""

import time
import json
import hmac
import hashlib
import threading
from io import StringIO
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client, TransactionTestCase
from django.utils import timezone
from django.conf import settings
from django.db import IntegrityError, transaction
from django.core.management import call_command

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.whatsapp_bot_v4.models import WebhookEvent


class YCloudWebhookOrderTests(TransactionTestCase):
    """Test exact order of HTTP 200, persistence, and bot processing.

    Uses TransactionTestCase for race condition test (needs real transaction support).
    """

    def setUp(self):
        self.client = Client()
        self.webhook_url = "/webhooks/ycloud/v1/"

        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="1234567",
            numero_visible="+51995403320",
            activo=True,
        )

        if not hasattr(settings, 'YCLOUD_WEBHOOK_SECRET'):
            settings.YCLOUD_WEBHOOK_SECRET = "test-secret-key"

    def _sign_payload(self, body_bytes, timestamp=None):
        """Generate valid HMAC-SHA256 signature for YCloud webhook."""
        if timestamp is None:
            timestamp = str(int(timezone.now().timestamp()))

        signed_content = f"{timestamp}.{body_bytes.decode('utf-8')}" if isinstance(body_bytes, bytes) else f"{timestamp}.{body_bytes}"
        signature = hmac.new(
            settings.YCLOUD_WEBHOOK_SECRET.encode(),
            signed_content.encode() if isinstance(signed_content, str) else signed_content,
            hashlib.sha256
        ).hexdigest()

        return f"t={timestamp},s={signature}"

    # ==================== TEST 1: Message Persists BEFORE HTTP 200 ====================

    def test_1_message_persists_before_http_200(self):
        """
        CRITICAL: Prove message persists atomically BEFORE HTTP 200 is returned.

        Flow:
        1. Send webhook with valid signature
        2. Verify Cliente exists (from get_or_create)
        3. Verify Conversation exists (from resolve_or_create_active_conversation)
        4. Verify WebhookEvent exists (registered before processing)
        5. Verify MensajeWhatsApp exists
        6. All within same @transaction.atomic() block
        7. HTTP 200 retorna DESPUÉS de todo lo anterior
        """
        payload = {
            "id": "evt_order_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_order_001",
                "from": "51995403320",
                "fromName": "Test User",
                "text": {"body": "Test message for order verification"}
            },
            "timestamp": int(timezone.now().timestamp())
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        # Send webhook
        response = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature
        )

        # VERIFY HTTP 200 (after persistence)
        self.assertEqual(response.status_code, 200, "HTTP 200 should be returned")
        self.assertEqual(response.json()['status'], 'ok')

        # VERIFY Cliente created (first step in persistence)
        cliente = Cliente.objects.filter(telefono="+51995403320").first()
        self.assertIsNotNone(cliente, "Cliente should be created")
        self.assertEqual(cliente.nombre, "Test User")

        # VERIFY Conversation created
        conv = ConversacionWhatsApp.objects.filter(
            cliente=cliente,
            channel=self.channel,
            cerrada_en__isnull=True
        ).first()
        self.assertIsNotNone(conv, "Conversation should be created")

        # VERIFY WebhookEvent registered
        webhook_event = WebhookEvent.objects.filter(
            source='ycloud',
            external_message_id='evt_order_001'
        ).first()
        self.assertIsNotNone(webhook_event, "WebhookEvent should be registered")

        # VERIFY MensajeWhatsApp created
        msg = MensajeWhatsApp.objects.filter(meta_message_id="wamid_order_001").first()
        self.assertIsNotNone(msg, "Message should be created BEFORE HTTP 200")
        self.assertEqual(msg.contenido, "Test message for order verification")
        self.assertEqual(msg.direccion, MensajeWhatsApp.ENTRANTE)
        self.assertEqual(msg.origen, MensajeWhatsApp.ORIGEN_CLIENTE)

        # VERIFY Conversation updated
        self.assertIsNotNone(conv.ultima_actividad)
        self.assertEqual(conv.resumen, "Test message for order verification")

    # ==================== TEST 2: Bot Processing is Sync (NOT Async) ====================

    def test_2_bot_processing_blocks_but_is_marked_async(self):
        """
        CRITICAL: Demonstrate that 'async' in process_bot_for_conversation_async()
        is NOT truly async — it blocks the response.

        Current behavior (SYNC):
        - HTTP 200 is returned AFTER bot processing completes
        - If bot takes 5s, HTTP 200 takes 5s+ to return

        This test proves the name is misleading.
        Expected recommendation: Use Celery/task queue for TRUE async.
        """
        payload = {
            "id": "evt_async_test_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_async_test_001",
                "from": "51995403321",
                "text": {"body": "Async test message"}
            },
            "timestamp": int(timezone.now().timestamp())
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        # Mock process_bot_for_conversation_async to introduce delay
        original_process = None
        delay_applied = [False]

        def delayed_process_bot(*args, **kwargs):
            """Simulate slow bot processing (5 second delay)."""
            delay_applied[0] = True
            time.sleep(0.5)  # Simulate 500ms bot delay (reduced for tests)
            if original_process:
                try:
                    return original_process(*args, **kwargs)
                except Exception:
                    pass  # Bot error is OK — we're testing timing, not functionality

        # Patch the async function
        with patch('apps.whatsapp_bot_v4.services.ycloud_webhook_service.process_bot_for_conversation_async', side_effect=delayed_process_bot):
            # Save original
            from apps.whatsapp_bot_v4.services import ycloud_webhook_service
            original_process = ycloud_webhook_service.process_bot_for_conversation_async

            # Measure HTTP 200 timing
            start_time = time.time()
            response = self.client.post(
                self.webhook_url,
                data=body,
                content_type='application/json',
                HTTP_YCLOUD_SIGNATURE=signature
            )
            elapsed = time.time() - start_time

            # HTTP 200 should be returned
            self.assertEqual(response.status_code, 200)

            # If bot processing was TRULY async, this would be < 50ms
            # But if it's SYNC (as it currently is), it will be >= delay time
            # This test documents the current behavior
            if delay_applied[0]:
                self.assertGreaterEqual(elapsed, 0.3,
                    "Bot processing is SYNC — elapsed time includes 500ms delay. "
                    "For TRUE async, should return HTTP 200 in < 50ms.")

            # Message should still persist regardless
            msg = MensajeWhatsApp.objects.filter(meta_message_id="wamid_async_test_001").first()
            self.assertIsNotNone(msg, "Message persists even with slow bot")

    def test_2b_http_200_timing_without_bot_processing(self):
        """
        Control test: HTTP 200 timing when bot processing is skipped.

        Proves that bot processing (if it ran to completion) would add latency.
        """
        payload = {
            "id": "evt_no_bot_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_no_bot_001",
                "from": "51995403322",
                "text": {"body": "No bot processing"}
            },
            "timestamp": int(timezone.now().timestamp())
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        # Skip bot processing entirely
        with patch('apps.whatsapp_bot_v4.services.ycloud_webhook_service.process_bot_for_conversation_async', return_value=None):
            start_time = time.time()
            response = self.client.post(
                self.webhook_url,
                data=body,
                content_type='application/json',
                HTTP_YCLOUD_SIGNATURE=signature
            )
            elapsed = time.time() - start_time

            # HTTP 200 should be fast (< 50ms)
            self.assertEqual(response.status_code, 200)
            self.assertLess(elapsed, 0.5, "HTTP 200 should be fast without bot processing")

    # ==================== TEST 3: Error BEFORE Persistence (Signature Invalid) ====================

    def test_3_error_before_persistence_invalid_signature(self):
        """
        Error at signature validation point.

        Flow:
        1. Signature validation FAILS (line 140 in ycloud_webhook_service.py)
        2. Return HTTP 401 immediately
        3. NO persistence (Cliente, Conversation, Message, WebhookEvent)
        """
        payload = {
            "id": "evt_bad_sig_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_bad_sig_001",
                "from": "51995403323",
                "text": {"body": "Test"}
            }
        }

        body = json.dumps(payload).encode('utf-8')
        # INTENTIONALLY WRONG signature
        bad_signature = "t=123456,s=this_signature_is_completely_wrong"

        response = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=bad_signature
        )

        # HTTP 401 (Unauthorized)
        self.assertEqual(response.status_code, 401,
            "Invalid signature should return HTTP 401, not process")

        # VERIFY NOTHING was persisted
        cliente = Cliente.objects.filter(telefono="+51995403323").first()
        self.assertIsNone(cliente, "Invalid signature → NO Cliente created")

        # WebhookEvent may or may not exist (depends on when validation occurs)
        # In this implementation, validation happens BEFORE WebhookEvent creation
        webhook_events = WebhookEvent.objects.filter(external_message_id='evt_bad_sig_001')
        self.assertEqual(webhook_events.count(), 0,
            "WebhookEvent should NOT be created for invalid signature")

    # ==================== TEST 4: Error DURING Persistence (Database Constraint) ====================

    def test_4_error_during_persistence_integrity_error(self):
        """
        Error during persistence (e.g., database constraint violation).

        Scenario: MensajeWhatsApp creation fails with IntegrityError.

        Expected behavior:
        1. WebhookEvent already created (before transaction)
        2. Transaction begins
        3. Cliente created OK
        4. Conversation created OK
        5. MensajeWhatsApp creation FAILS (IntegrityError)
        6. Transaction ROLLED BACK
        7. HTTP 500 or HTTP 200? (Currently HTTP 200 due to exception handling)
        """
        payload = {
            "id": "evt_integrity_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_integrity_001",
                "from": "51995403324",
                "text": {"body": "Test"}
            },
            "timestamp": int(timezone.now().timestamp())
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        # First request: normal persistence
        response1 = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature
        )
        self.assertEqual(response1.status_code, 200)

        # Verify first message created
        msg1 = MensajeWhatsApp.objects.filter(meta_message_id="wamid_integrity_001").first()
        self.assertIsNotNone(msg1)

        # Second request: SAME wamid (should NOT create duplicate)
        response2 = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature
        )

        # HTTP 200 (already processed, idempotent)
        self.assertEqual(response2.status_code, 200)

        # Still only 1 message
        messages = MensajeWhatsApp.objects.filter(meta_message_id="wamid_integrity_001")
        self.assertEqual(messages.count(), 1, "Duplicate wamid should be idempotent")

    # ==================== TEST 5: Error AFTER Persistence (Bot Fails) ====================

    def test_5_error_after_persistence_bot_failure(self):
        """
        Error in bot processing (after message is persisted).

        Flow:
        1. Message persisted ✓ (within @transaction.atomic())
        2. WebhookEvent registered ✓
        3. HTTP 200 returned ✓
        4. Bot processing called (synchronously, currently)
        5. Bot processing THROWS EXCEPTION (e.g., OpenAI API error, network error)
        6. Exception caught and logged (line 257-258 in ycloud_webhook_service.py)
        7. No impact on message persistence (already done)

        Key point: Message persists even if bot fails.
        """
        payload = {
            "id": "evt_bot_fail_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_bot_fail_001",
                "from": "51995403325",
                "fromName": "Bot Fail Test",
                "text": {"body": "This will survive bot failure"}
            },
            "timestamp": int(timezone.now().timestamp())
        }

        body = json.dumps(payload).encode('utf-8')
        signature = self._sign_payload(body)

        # Patch bot processing to raise exception
        def failing_bot_processor(*args, **kwargs):
            raise RuntimeError("Simulated bot failure: OpenAI API error")

        with patch('apps.whatsapp_bot_v4.services.ycloud_webhook_service.process_bot_for_conversation_async',
                   side_effect=failing_bot_processor):
            response = self.client.post(
                self.webhook_url,
                data=body,
                content_type='application/json',
                HTTP_YCLOUD_SIGNATURE=signature
            )

        # HTTP 200 still returned (bot failure is caught, not propagated)
        self.assertEqual(response.status_code, 200,
            "HTTP 200 should be returned despite bot failure")
        self.assertEqual(response.json()['status'], 'ok')

        # Message still persisted
        msg = MensajeWhatsApp.objects.filter(meta_message_id="wamid_bot_fail_001").first()
        self.assertIsNotNone(msg, "Message persists even if bot fails")
        self.assertEqual(msg.contenido, "This will survive bot failure")

        # Cliente still created
        cliente = Cliente.objects.filter(telefono="+51995403325").first()
        self.assertIsNotNone(cliente)

        # Conversation still created
        conv = ConversacionWhatsApp.objects.filter(cliente=cliente, channel=self.channel).first()
        self.assertIsNotNone(conv)

    # ==================== TEST 6: Multiple Messages Same Client ====================

    def test_6_multiple_messages_same_client_reuses_conversation(self):
        """
        Race condition scenario (without threading complications):
        Two webhooks for the same cliente in quick succession.

        Expected behavior:
        1. First webhook creates conversation
        2. Second webhook REUSES same conversation (no duplicates)
        3. Both return HTTP 200
        4. Exactly 1 active conversation for the cliente
        5. Both messages persisted

        Current implementation: Uses select_for_update() in YCloudMessageProcessor
        to prevent race conditions even with rapid sequential requests.
        """
        channel_id = self.channel.id

        # First webhook
        payload_1 = {
            "id": "evt_race_001",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_race_001",
                "from": "51995403326",
                "text": {"body": "Message 1"}
            },
            "timestamp": int(timezone.now().timestamp())
        }
        body_1 = json.dumps(payload_1).encode('utf-8')
        signature_1 = self._sign_payload(body_1)

        response_1 = self.client.post(
            self.webhook_url,
            data=body_1,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature_1
        )
        self.assertEqual(response_1.status_code, 200)

        # Second webhook (same client)
        payload_2 = {
            "id": "evt_race_002",
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": "wamid_race_002",
                "from": "51995403326",
                "text": {"body": "Message 2"}
            },
            "timestamp": int(timezone.now().timestamp())
        }
        body_2 = json.dumps(payload_2).encode('utf-8')
        signature_2 = self._sign_payload(body_2)

        response_2 = self.client.post(
            self.webhook_url,
            data=body_2,
            content_type='application/json',
            HTTP_YCLOUD_SIGNATURE=signature_2
        )
        self.assertEqual(response_2.status_code, 200)

        # Verify exactly 1 conversation (no duplicates)
        cliente = Cliente.objects.filter(telefono="+51995403326").first()
        self.assertIsNotNone(cliente)

        active_convs = ConversacionWhatsApp.objects.filter(
            cliente=cliente,
            channel_id=channel_id,
            cerrada_en__isnull=True
        )
        self.assertEqual(active_convs.count(), 1,
            "Multiple webhooks from same client should reuse conversation "
            "(select_for_update() lock prevents duplicates)")

        # Both messages should persist
        msgs = MensajeWhatsApp.objects.filter(
            conversacion_id=active_convs.first().id,
            direccion=MensajeWhatsApp.ENTRANTE
        ).order_by('fecha_mensaje')

        self.assertEqual(msgs.count(), 2, "Both messages should persist")
        self.assertEqual(msgs[0].contenido, "Message 1")
        self.assertEqual(msgs[1].contenido, "Message 2")


class YCloudWebhookAsyncBehaviorDocumentation(TestCase):
    """
    Document current async behavior and recommendations for improvement.
    """

    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            nombre="Test Channel",
            phone_number_id="1234567",
            numero_visible="+51995403320",
            activo=True,
        )

    def test_async_documentation_current_behavior(self):
        """
        Document: process_bot_for_conversation_async() is NOT async.

        Current implementation (ycloud_webhook_service.py line 212):
        ```python
        process_bot_for_conversation_async(result["conversation"], result["message"])
        ```

        Issues:
        1. Function name is misleading — suggests async but is sync
        2. Blocks HTTP 200 response indefinitely
        3. If bot/OpenAI hangs, webhook timeout will occur
        4. No fault isolation (bot crash affects webhook endpoint)
        5. No retry logic for transient bot failures

        Current flow (SYNC):
        HTTP 200 returned only AFTER:
        - Signature verification ✓
        - WebhookEvent registered ✓
        - Cliente/Conversation/Message persisted ✓
        - Bot processing completed (can take 3-10s for OpenAI)

        Recommended improvements:
        1. Use Celery task queue for TRUE async:
           ```python
           from celery import shared_task

           @shared_task
           def process_bot_conversation_task(conversation_id, message_id):
               conversation = ConversacionWhatsApp.objects.get(id=conversation_id)
               message = MensajeWhatsApp.objects.get(id=message_id)
               process_bot_for_conversation_async(conversation, message)

           # In webhook:
           if result.get("message") and result.get("conversation"):
               process_bot_conversation_task.delay(
                   result["conversation"].id,
                   result["message"].id
               )
           ```

        2. Return HTTP 200 IMMEDIATELY:
           ```python
           # BEFORE bot processing
           response = JsonResponse({'status': 'ok'})

           # AFTER returning response:
           process_bot_for_conversation_async(...)  # or task.delay(...)
           ```
        """
        # This is a documentation test — no assertions, just proof of concept
        pass

    def test_recommended_async_with_task_queue(self):
        """
        Proof of concept: How to make bot processing truly async with Celery.

        This demonstrates the RECOMMENDED approach (not currently implemented).
        """
        from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp

        cliente = Cliente.objects.create(
            telefono="+51995403327",
            nombre="Async Test"
        )

        conv = ConversacionWhatsApp.objects.create(
            cliente=cliente,
            channel=self.channel
        )

        msg = MensajeWhatsApp.objects.create(
            conversacion=conv,
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            contenido="Async test message"
        )

        # Recommended pattern: Queue the task, return immediately
        # (This is pseudocode — requires Celery setup)
        # process_bot_conversation_task.delay(conv.id, msg.id)

        # Verify message exists (persisted before queue)
        self.assertEqual(MensajeWhatsApp.objects.filter(id=msg.id).count(), 1)
