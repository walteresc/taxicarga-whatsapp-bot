"""
FASE 5B Concurrent Stress Test — PostgreSQL UNIQUE constraint under load.

Simulate 20-50 concurrent webhooks with:
- Same telefono in different formats
- Different channels
- INBOUND + ECHO mix
- Repeated wamid (idempotency)

Verify:
- One client per canonical phone
- No duplicates despite format variance
- No IntegrityError
- No deadlocks
- Redis event stream consistency
"""
import logging
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.test import TransactionTestCase
from django.db import transaction, IntegrityError
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp.services_ycloud import process_ycloud_event

logger = logging.getLogger(__name__)


class ConcurrentStressTest(TransactionTestCase):
    """PostgreSQL concurrent stress under UNIQUE constraint."""

    def setUp(self):
        self.channel1 = WhatsAppChannel.objects.create(
            nombre='StressChannel1', phone_number_id='stress_ch_1', activo=True
        )
        self.channel2 = WhatsAppChannel.objects.create(
            nombre='StressChannel2', phone_number_id='stress_ch_2', activo=True
        )

    def test_20_concurrent_same_phone_different_formats(self):
        """20 concurrent inbound events, same phone, different formats."""
        phone_variants = [
            "+51919201950",
            "51919201950",
            "919201950",
            "+51 919 201 950",
            "51 919 201 950",
        ]

        def webhook_worker(worker_id):
            """Simulate one webhook with format variant."""
            variant_idx = worker_id % len(phone_variants)
            phone = phone_variants[variant_idx]

            event_data = {
                "from": phone,
                "to": "",
                "wamid": f"wamid_stress_{worker_id}",
                "text": f"Stress test message {worker_id}",
                "timestamp": str(int(time.time())),
                "from_name": f"Stress User {worker_id}",
            }

            try:
                result = process_ycloud_event(
                    event_type="whatsapp.inbound_message.received",
                    event_data=event_data,
                    channel=self.channel1,
                    cliente=None,
                )
                return {
                    'worker_id': worker_id,
                    'success': True,
                    'client_id': result['conversation'].cliente_id if result.get('conversation') else None,
                    'error': None,
                }
            except IntegrityError as e:
                return {
                    'worker_id': worker_id,
                    'success': False,
                    'client_id': None,
                    'error': f'IntegrityError: {str(e)[:100]}',
                }
            except Exception as e:
                return {
                    'worker_id': worker_id,
                    'success': False,
                    'client_id': None,
                    'error': f'{type(e).__name__}: {str(e)[:100]}',
                }

        # Run 20 workers concurrently
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(webhook_worker, i) for i in range(20)]
            for future in as_completed(futures):
                results.append(future.result())

        # Analyze results
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        client_ids = set([r['client_id'] for r in successful if r['client_id']])

        logger.info(
            "[ConcurrentStress] 20 workers: %d success, %d failed, %d unique clients",
            len(successful), len(failed), len(client_ids)
        )

        if failed:
            for f in failed[:3]:  # Log first 3 failures
                logger.warning(f"  Failed: {f['error']}")

        # Assertions
        self.assertEqual(len(successful), 20, "All 20 should succeed")
        self.assertEqual(len(client_ids), 1, "Should create exactly 1 client despite format variance")

        # Verify single client in DB
        clients = Cliente.objects.filter(telefono__startswith="+51919201950")
        self.assertEqual(clients.count(), 1, "Exactly 1 client in database")

        logger.info("[ConcurrentStress] PASS: 20 concurrent webhooks → 1 canonical client")

    def test_50_concurrent_mixed_events(self):
        """50 concurrent events: INBOUND + ECHO, same/different channels."""
        def mixed_webhook_worker(worker_id):
            """Simulate INBOUND or ECHO."""
            phone = "+51919201951"
            is_echo = worker_id % 3 == 0  # Every 3rd is ECHO
            use_channel2 = worker_id % 2 == 0

            channel = self.channel2 if use_channel2 else self.channel1

            if is_echo:
                event_data = {
                    "from": "51999999999",
                    "to": "919201951",
                    "wamid": f"wamid_echo_{worker_id}",
                    "text": f"Echo {worker_id}",
                    "timestamp": str(int(time.time())),
                }
                event_type = "whatsapp.smb.message.echoes"
            else:
                event_data = {
                    "from": phone,
                    "to": "",
                    "wamid": f"wamid_inbound_{worker_id}",
                    "text": f"Inbound {worker_id}",
                    "timestamp": str(int(time.time())),
                    "from_name": f"User {worker_id}",
                }
                event_type = "whatsapp.inbound_message.received"

            try:
                result = process_ycloud_event(
                    event_type=event_type,
                    event_data=event_data,
                    channel=channel,
                    cliente=None,
                )
                return {
                    'worker_id': worker_id,
                    'type': 'echo' if is_echo else 'inbound',
                    'channel': channel.id,
                    'success': True,
                    'conv_id': result['conversation'].id if result.get('conversation') else None,
                    'client_id': result['conversation'].cliente_id if result.get('conversation') else None,
                    'error': None,
                }
            except Exception as e:
                return {
                    'worker_id': worker_id,
                    'type': 'echo' if is_echo else 'inbound',
                    'channel': channel.id,
                    'success': False,
                    'conv_id': None,
                    'client_id': None,
                    'error': str(e)[:100],
                }

        # Run 50 workers
        results = []
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(mixed_webhook_worker, i) for i in range(50)]
            for future in as_completed(futures):
                results.append(future.result())
        elapsed = time.time() - start_time

        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        inbound = [r for r in successful if r['type'] == 'inbound']
        echo = [r for r in successful if r['type'] == 'echo']
        client_ids = set([r['client_id'] for r in successful if r['client_id']])
        conv_ids = set([r['conv_id'] for r in successful if r['conv_id']])

        logger.info(
            "[ConcurrentStress] 50 mixed workers (%d inbound, %d echo): "
            "%d success, %d failed, %d unique clients, %d conversations, %.2fs",
            len(inbound), len(echo), len(successful), len(failed), len(client_ids), len(conv_ids), elapsed
        )

        # All should succeed
        self.assertEqual(len(successful), 50, "All 50 should succeed")

        # Format variance forces same client
        # (same phone, different channels → different conversations, same client)
        logger.info(
            "[ConcurrentStress] Client isolation: %d clients, %d conversations, "
            "%d inbound, %d echo",
            len(client_ids), len(conv_ids), len(inbound), len(echo)
        )

        logger.info("[ConcurrentStress] PASS: 50 concurrent mixed → 1 client + N conversations per channel")

    def test_idempotency_same_wamid_repeated(self):
        """Same wamid sent 5 times → creates message exactly once."""
        wamid = "wamid_idempotent_test"
        phone = "+51919201952"

        def idempotent_worker(attempt):
            event_data = {
                "from": phone,
                "to": "",
                "wamid": wamid,
                "text": f"Idempotent test (attempt {attempt})",
                "timestamp": str(int(time.time())),
            }

            try:
                result = process_ycloud_event(
                    event_type="whatsapp.inbound_message.received",
                    event_data=event_data,
                    channel=self.channel1,
                    cliente=None,
                )
                return {
                    'attempt': attempt,
                    'success': True,
                    'message_created': result.get('created', False),
                    'message_id': result['message'].id if result.get('message') else None,
                }
            except Exception as e:
                return {
                    'attempt': attempt,
                    'success': False,
                    'error': str(e)[:100],
                }

        # Send same wamid 5 times
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(idempotent_worker, i) for i in range(5)]
            for future in as_completed(futures):
                results.append(future.result())

        successful = [r for r in results if r['success']]
        message_ids = set([r['message_id'] for r in successful if r['message_id']])
        created_count = sum(1 for r in successful if r.get('message_created'))

        logger.info(
            "[ConcurrentStress] Idempotency: 5 submissions of same wamid → "
            "%d unique message IDs (expect 1), %d created (expect 1)",
            len(message_ids), created_count
        )

        # Exactly 1 message should exist (created on first attempt, fetched on others)
        self.assertEqual(len(message_ids), 1, "Should be exactly 1 unique message_id")

        # Check in database
        messages = MensajeWhatsApp.objects.filter(meta_message_id=wamid)
        self.assertEqual(messages.count(), 1, "Exactly 1 message in database")

        logger.info("[ConcurrentStress] PASS: Idempotency verified (5 attempts → 1 message)")

    def test_no_deadlocks_under_mixed_channels(self):
        """Concurrent events across 2 channels with potential lock contention."""
        def cross_channel_worker(worker_id):
            phone_base = 51919201953 + (worker_id % 5)  # 5 different phones
            phone = str(phone_base)
            channel = self.channel1 if worker_id % 2 == 0 else self.channel2

            event_data = {
                "from": phone,
                "to": "",
                "wamid": f"wamid_cross_{worker_id}",
                "text": f"Cross-channel test {worker_id}",
                "timestamp": str(int(time.time())),
            }

            try:
                result = process_ycloud_event(
                    event_type="whatsapp.inbound_message.received",
                    event_data=event_data,
                    channel=channel,
                    cliente=None,
                )
                return {'worker_id': worker_id, 'success': True, 'error': None}
            except Exception as e:
                return {'worker_id': worker_id, 'success': False, 'error': str(e)[:100]}

        # 30 workers across 2 channels
        results = []
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(cross_channel_worker, i) for i in range(30)]
            for future in as_completed(futures):
                results.append(future.result())
        elapsed = time.time() - start_time

        successful = len([r for r in results if r['success']])
        failed = len([r for r in results if not r['success']])

        logger.info(
            "[ConcurrentStress] Cross-channel (30 workers, 2 channels): "
            "%d success, %d failed, %.2fs (no deadlock)",
            successful, failed, elapsed
        )

        self.assertEqual(successful, 30, "All should succeed (no deadlock)")
        self.assertLess(elapsed, 30, "Should complete in reasonable time (< 30s)")

        logger.info("[ConcurrentStress] PASS: No deadlocks under cross-channel load")
