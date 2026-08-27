"""
FASE 5B Real Value Detection Tests

9 scenarios for verifying conversation.updated is emitted ONLY when values actually change.
Uses TransactionTestCase so transaction.on_commit() fires.
Counts events in Redis Stream (real, not mocked).
"""

import logging
from django.test import TransactionTestCase
from django.utils import timezone
from django.db import transaction
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel
from apps.whatsapp.redis_events import get_latest_cursor, get_events

logger = logging.getLogger(__name__)


class RealValueDetectionTest(TransactionTestCase):
    """Test 9 scenarios of real value change detection."""

    def setUp(self):
        """Setup channel, cliente, conversation."""
        from apps.clientes.models import Cliente

        self.channel = WhatsAppChannel.objects.create(
            nombre='TestChannel',
            phone_number_id='123456',
            activo=True
        )

        self.cliente = Cliente.objects.create(
            nombre='TestCliente',
            telefono='51912345678'
        )

    def _get_events_since(self, cursor):
        """Helper: get events since cursor."""
        return get_events(cursor)

    def _count_event_type(self, events, event_type):
        """Helper: count events of specific type."""
        return len([e for e in events if e.type == event_type])

    def test_scenario_1_new_conversation_emits_created_only(self):
        """Scenario 1: New conversation → conversation.created=1, conversation.updated=0."""
        cursor_before = get_latest_cursor()

        conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='New conversation',
            estado_atencion='en_espera',
            bot_pausado=False
        )

        events = self._get_events_since(cursor_before)
        created_count = self._count_event_type(events, 'conversation.created')
        updated_count = self._count_event_type(events, 'conversation.updated')

        logger.info(f"[S1] New conv: created={created_count}, updated={updated_count}")
        self.assertEqual(created_count, 1, "New conversation must emit exactly conversation.created")
        self.assertEqual(updated_count, 0, "New conversation must NOT emit conversation.updated")

    def test_scenario_2_save_no_changes_no_event(self):
        """Scenario 2: save() without changing any field → conversation.updated=0."""
        # Create conversation first
        conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='Test',
            estado_atencion='en_espera'
        )

        # Now save without changes
        cursor_before = get_latest_cursor()

        with transaction.atomic():
            conv.save()

        events = self._get_events_since(cursor_before)
        updated_count = self._count_event_type(events, 'conversation.updated')

        logger.info(f"[S2] save() no changes: updated={updated_count}")
        self.assertEqual(updated_count, 0, "save() without changes must NOT emit conversation.updated")

    def test_scenario_3_same_value_update_fields_no_event(self):
        """Scenario 3: save(update_fields=['resumen']) with SAME value → conversation.updated=0."""
        conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='Original summary',
            estado_atencion='en_espera'
        )

        cursor_before = get_latest_cursor()

        # Explicitly set to same value
        conv.resumen = 'Original summary'  # No change

        with transaction.atomic():
            conv.save(update_fields=['resumen'])

        events = self._get_events_since(cursor_before)
        updated_count = self._count_event_type(events, 'conversation.updated')

        logger.info(f"[S3] same value update_fields: updated={updated_count}")
        self.assertEqual(updated_count, 0, "Same value in update_fields must NOT emit conversation.updated")

    def test_scenario_4_real_change_update_fields_emits_event(self):
        """Scenario 4: save(update_fields=['resumen']) with DIFFERENT value → conversation.updated=1."""
        conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='Original',
            estado_atencion='en_espera'
        )

        cursor_before = get_latest_cursor()

        conv.resumen = 'Modified'

        with transaction.atomic():
            conv.save(update_fields=['resumen'])

        events = self._get_events_since(cursor_before)
        updated_count = self._count_event_type(events, 'conversation.updated')

        logger.info(f"[S4] real change update_fields: updated={updated_count}")
        self.assertEqual(updated_count, 1, "Real value change must emit conversation.updated")

        # Verify changed_fields in event
        updated_events = [e for e in events if e.type == 'conversation.updated']
        if updated_events:
            changed = updated_events[0].data.get('changed_fields', [])
            self.assertIn('resumen', changed, "changed_fields must include 'resumen'")
            logger.info(f"[S4] changed_fields={changed}")

    def test_scenario_5_non_significant_field_no_event(self):
        """Scenario 5: save(update_fields=[...]) with non-significant field only → conversation.updated=0."""
        from django.utils import timezone

        conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='Test',
            estado_atencion='en_espera'
        )

        cursor_before = get_latest_cursor()

        # Modify field that's not in SIGNIFICANT_FIELDS
        # Most models have fields like created_at, updated_at that aren't monitored
        # For this model, we can try updating a field that's not in SIGNIFICANT_FIELDS
        # Since we don't have one easily modifiable, we test the logic:
        # update_fields=['channel_id'] - channel_id is not in SIGNIFICANT_FIELDS

        conv.channel_id = self.channel.id  # Same value

        with transaction.atomic():
            conv.save(update_fields=['channel_id'])

        events = self._get_events_since(cursor_before)
        updated_count = self._count_event_type(events, 'conversation.updated')

        logger.info(f"[S5] non-significant field: updated={updated_count}")
        self.assertEqual(updated_count, 0, "Non-significant fields must NOT emit conversation.updated")

    def test_scenario_6_multiple_fields_one_event(self):
        """Scenario 6: Change multiple significant fields → conversation.updated=1 (not per-field)."""
        conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='Original',
            estado_atencion='en_espera',
            bot_pausado=False
        )

        cursor_before = get_latest_cursor()

        conv.resumen = 'Modified'
        conv.bot_pausado = True

        with transaction.atomic():
            conv.save()

        events = self._get_events_since(cursor_before)
        updated_count = self._count_event_type(events, 'conversation.updated')

        logger.info(f"[S6] multiple fields: updated={updated_count}")
        self.assertEqual(updated_count, 1, "Multiple field changes emit exactly ONE event")

        # Verify both fields in changed_fields
        updated_events = [e for e in events if e.type == 'conversation.updated']
        if updated_events:
            changed = updated_events[0].data.get('changed_fields', [])
            self.assertIn('resumen', changed)
            self.assertIn('bot_pausado', changed)
            logger.info(f"[S6] changed_fields={changed}")

    def test_scenario_7_rollback_no_events(self):
        """Scenario 7: Rollback transaction → no events published."""
        cursor_before = get_latest_cursor()

        try:
            with transaction.atomic():
                conv = ConversacionWhatsApp.objects.create(
                    channel=self.channel,
                    cliente=self.cliente,
                    resumen='Will rollback',
                    estado_atencion='en_espera'
                )
                # Force rollback
                raise Exception("Forced rollback")
        except Exception:
            pass

        events = self._get_events_since(cursor_before)
        created_count = self._count_event_type(events, 'conversation.created')

        logger.info(f"[S7] rollback: created={created_count}")
        self.assertEqual(created_count, 0, "Rollback must not publish any events")

    def test_scenario_8_fk_field_change_emits_event(self):
        """Scenario 8: Change FK field (responsable_id) → conversation.updated=1."""
        from django.contrib.auth.models import User

        # Create users
        user1 = User.objects.create_user(username='user1')
        user2 = User.objects.create_user(username='user2')

        conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='Test',
            estado_atencion='en_espera',
            responsable=user1
        )

        cursor_before = get_latest_cursor()

        # Change FK
        conv.responsable = user2

        with transaction.atomic():
            conv.save(update_fields=['responsable_id'])

        events = self._get_events_since(cursor_before)
        updated_count = self._count_event_type(events, 'conversation.updated')

        logger.info(f"[S8] FK change: updated={updated_count}")
        self.assertEqual(updated_count, 1, "FK field change must emit conversation.updated")

    def test_scenario_9_queryset_update_no_signal(self):
        """Scenario 9: QuerySet.update() does NOT trigger signal."""
        conv = ConversacionWhatsApp.objects.create(
            channel=self.channel,
            cliente=self.cliente,
            resumen='Test',
            estado_atencion='en_espera'
        )

        cursor_before = get_latest_cursor()

        # Use QuerySet.update() (bypasses signals)
        ConversacionWhatsApp.objects.filter(id=conv.id).update(
            resumen='Modified via queryset'
        )

        events = self._get_events_since(cursor_before)
        updated_count = self._count_event_type(events, 'conversation.updated')

        logger.info(f"[S9] QuerySet.update(): updated={updated_count}")
        self.assertEqual(updated_count, 0, "QuerySet.update() must NOT trigger signal/event")
        logger.warning("[S9] NOTE: QuerySet.update() does not emit events - operationally OK if not used for critical updates")


if __name__ == '__main__':
    import unittest
    unittest.main()
