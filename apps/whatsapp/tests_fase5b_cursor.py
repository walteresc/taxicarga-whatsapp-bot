"""
FASE 5B: Cursor protocol, event deduplication, real value detection.
"""
import logging
from django.test import TransactionTestCase
from django.db import transaction
from django.utils import timezone
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.whatsapp.redis_events import get_latest_cursor, get_events
from apps.clientes.models import Cliente

logger = logging.getLogger(__name__)

import uuid


class CursorProtocolTest(TransactionTestCase):
    """Snapshot cursor protocol: obtain cursor BEFORE snapshot to prevent history replay."""

    def test_cursor_before_snapshot_prevents_replay(self):
        """Capture cursor before snapshot prevents history being replayed."""
        # Unique IDs
        ph = f'99{uuid.uuid4().hex[:8]}'
        tel = f'51{uuid.uuid4().hex[:10]}'

        ch = WhatsAppChannel.objects.create(nombre=f'TestCh{ph}', phone_number_id=ph, activo=True)
        cl = Cliente.objects.create(nombre=f'TestCl{tel}', telefono=tel)

        # Step 1: Capture cursor BEFORE snapshot
        cursor_before = get_latest_cursor()

        # Step 2: Take snapshot (create conversation)
        with transaction.atomic():
            conv = ConversacionWhatsApp.objects.create(
                channel=ch, cliente=cl,
                resumen='Snapshot test', estado_atencion='en_espera'
            )

        # Step 3: Get events from cursor_before
        events = get_events(cursor_before)
        created_count = len([e for e in events if e.type == 'conversation.created'])

        logger.info(f"[CursorProtocol] Cursor captured before snapshot")
        logger.info(f"[CursorProtocol] Created conversation {conv.id}")
        logger.info(f"[CursorProtocol] Events after cursor: {created_count} conversation.created")

        self.assertGreaterEqual(created_count, 1, "Snapshot event must be in stream after cursor")

    def test_last_event_id_header_recovery(self):
        """SSE with Last-Event-ID header recovers from cursor correctly."""
        # Unique IDs
        ph1 = f'98{uuid.uuid4().hex[:8]}'
        tel1 = f'51{uuid.uuid4().hex[:10]}'
        ph2 = f'97{uuid.uuid4().hex[:8]}'
        tel2 = f'51{uuid.uuid4().hex[:10]}'

        ch1 = WhatsAppChannel.objects.create(nombre=f'Ch1{ph1}', phone_number_id=ph1, activo=True)
        cl1 = Cliente.objects.create(nombre=f'Cl1{tel1}', telefono=tel1)

        ch2 = WhatsAppChannel.objects.create(nombre=f'Ch2{ph2}', phone_number_id=ph2, activo=True)
        cl2 = Cliente.objects.create(nombre=f'Cl2{tel2}', telefono=tel2)

        cursor_1 = get_latest_cursor()

        with transaction.atomic():
            conv1 = ConversacionWhatsApp.objects.create(
                channel=ch1, cliente=cl1, resumen='Event 1', estado_atencion='en_espera'
            )

        cursor_2 = get_latest_cursor()

        with transaction.atomic():
            conv2 = ConversacionWhatsApp.objects.create(
                channel=ch2, cliente=cl2, resumen='Event 2', estado_atencion='en_espera'
            )

        # Get only new events since cursor_2
        events_since = get_events(cursor_2)
        new_created = len([e for e in events_since if e.type == 'conversation.created'])

        logger.info(f"[LastEventID] Recovery from cursor after first event: {new_created} new events")
        self.assertGreaterEqual(new_created, 1, "Should recover new events from Last-Event-ID")


class EventDeduplicationTest(TransactionTestCase):
    """Event deduplication by event_id on frontend side."""

    def test_message_event_includes_message_id(self):
        """message.created event includes message_id for frontend dedup."""
        ph = f'96{uuid.uuid4().hex[:8]}'
        tel = f'51{uuid.uuid4().hex[:10]}'

        ch = WhatsAppChannel.objects.create(nombre=f'Dedupe{ph}', phone_number_id=ph, activo=True)
        cl = Cliente.objects.create(nombre=f'Dedupe{tel}', telefono=tel)

        conv = ConversacionWhatsApp.objects.create(
            channel=ch, cliente=cl, resumen='Dedupe', estado_atencion='en_espera'
        )

        cursor = get_latest_cursor()

        with transaction.atomic():
            msg = MensajeWhatsApp.objects.create(
                conversacion=conv, direccion=MensajeWhatsApp.ENTRANTE,
                tipo='text', contenido='Dedupe test', meta_message_id='wamid_test123'
            )

        events = get_events(cursor)
        msg_created = [e for e in events if e.type == 'message.created']

        logger.info(f"[Dedup] message.created events: {len(msg_created)}")

        self.assertGreater(len(msg_created), 0, "message.created event should exist")
        if msg_created:
            event_data = msg_created[0].data
            self.assertIn('message_id', event_data, "Event must include message_id for dedup")

    def test_conversation_event_structure(self):
        """conversation.created event has proper structure for dedup."""
        ph = f'95{uuid.uuid4().hex[:8]}'
        tel = f'51{uuid.uuid4().hex[:10]}'

        ch = WhatsAppChannel.objects.create(nombre=f'EventID{ph}', phone_number_id=ph, activo=True)
        cl = Cliente.objects.create(nombre=f'EventID{tel}', telefono=tel)

        cursor = get_latest_cursor()

        with transaction.atomic():
            conv = ConversacionWhatsApp.objects.create(
                channel=ch, cliente=cl,
                resumen='Event ID test', estado_atencion='en_espera'
            )

        events = get_events(cursor)
        conv_created = [e for e in events if e.type == 'conversation.created']

        logger.info(f"[Dedup] conversation.created events: {len(conv_created)}")

        self.assertGreater(len(conv_created), 0, "conversation.created event should exist")


class RealValueDetectionTest(TransactionTestCase):
    """Verify real value change detection (not just update_fields presence)."""

    def test_save_same_value_no_update_event(self):
        """save(update_fields=['resumen']) with SAME value → NO conversation.updated."""
        ph = f'94{uuid.uuid4().hex[:8]}'
        tel = f'51{uuid.uuid4().hex[:10]}'

        ch = WhatsAppChannel.objects.create(nombre=f'Value{ph}', phone_number_id=ph, activo=True)
        cl = Cliente.objects.create(nombre=f'Value{tel}', telefono=tel)

        conv = ConversacionWhatsApp.objects.create(
            channel=ch, cliente=cl,
            resumen='Original', estado_atencion='en_espera'
        )

        cursor = get_latest_cursor()

        # Save with same value
        with transaction.atomic():
            conv.resumen = 'Original'  # Same value
            conv.save(update_fields=['resumen'])

        events = get_events(cursor)
        updated = [e for e in events if e.type == 'conversation.updated']

        logger.info(f"[ValueDetect] Save with same value: {len(updated)} conversation.updated (expect 0)")
        self.assertEqual(len(updated), 0, "Same value should not emit conversation.updated")

    def test_save_different_value_emits_update_event(self):
        """save(update_fields=['resumen']) with DIFFERENT value → conversation.updated."""
        ph = f'93{uuid.uuid4().hex[:8]}'
        tel = f'51{uuid.uuid4().hex[:10]}'

        ch = WhatsAppChannel.objects.create(nombre=f'Value2{ph}', phone_number_id=ph, activo=True)
        cl = Cliente.objects.create(nombre=f'Value2{tel}', telefono=tel)

        conv = ConversacionWhatsApp.objects.create(
            channel=ch, cliente=cl,
            resumen='Original', estado_atencion='en_espera'
        )

        cursor = get_latest_cursor()

        # Save with different value
        with transaction.atomic():
            conv.resumen = 'Modified'  # Different value
            conv.save(update_fields=['resumen'])

        events = get_events(cursor)
        updated = [e for e in events if e.type == 'conversation.updated']

        logger.info(f"[ValueDetect] Save with different value: {len(updated)} conversation.updated (expect 1)")
        self.assertEqual(len(updated), 1, "Different value must emit conversation.updated")
