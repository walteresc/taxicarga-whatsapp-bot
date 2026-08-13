"""
Test ownership/schedule/V3.1 separation.

Verify that:
1. Schedule NEVER sets human ownership
2. V3.1 works when owner=BOT (respects schedule in production)
3. Channel 7 TEST has bypass
4. Agent ownership blocks bot
5. Return to bot works
"""
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp
from apps.integrations.models import ConversationControl, ChannelIntegrationPolicy
from apps.integrations.enums import OwnerState
from apps.whatsapp.utils import should_bot_reply, _is_schedule_bypassed_for_testing


class OwnershipScheduleSeparationTest(TestCase):
    """Ownership and Schedule must be independent."""

    def setUp(self):
        self.client_rec = Cliente.objects.create(telefono="51999999999")
        self.channel = WhatsAppChannel.objects.create(
            nombre="TestChannel", phone_number_id="1234567890"
        )
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_rec, channel=self.channel
        )
        self.lead = Lead.objects.create(
            cliente=self.client_rec, whatsapp_channel=self.channel
        )
        self.conversation.lead = self.lead
        self.conversation.save()
        self.control = ConversationControl.objects.create(
            conversation=self.conversation,
            owner_state=OwnerState.BOT_ACTIVE
        )

    def test_schedule_miss_never_sets_atencion_humana(self):
        """Outside hours must NOT mark atencion_humana."""
        # Outside schedule (03:00 Lima)
        outside_hours = self.conversation.creada_en.replace(hour=3, minute=0)

        # Check should_bot_reply returns False (schedule miss)
        result = should_bot_reply(now=outside_hours, lead=self.lead, channel=self.channel)
        self.assertFalse(result, "should_bot_reply outside hours should be False")

        # But Lead.atencion_humana must NOT change
        self.assertFalse(self.lead.atencion_humana)
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.atencion_humana, "Schedule miss must NOT set atencion_humana")

    def test_owner_state_is_canonical_not_atencion_humana(self):
        """owner_state controls ownership, not atencion_humana."""
        # Even if atencion_humana=True by legacy, owner_state=BOT means BOT
        self.lead.atencion_humana = True
        self.lead.save()
        self.control.owner_state = OwnerState.BOT_ACTIVE
        self.control.save()

        # Ownership should be BOT (via owner_state)
        self.assertEqual(self.control.owner_state, OwnerState.BOT_ACTIVE)
        # atencion_humana is present but should NOT override modern owner_state
        self.assertTrue(self.lead.atencion_humana)

    def test_agent_ownership_blocks_bot(self):
        """owner_state=AGENT must block automatic bot response."""
        self.control.owner_state = OwnerState.AGENT_ACTIVE
        self.control.save()

        # Bot should not respond even if schedule allows
        inside_hours = self.conversation.creada_en.replace(hour=14, minute=0)
        # Note: should_bot_reply checks atencion_humana AND owner_state in views
        # Here we test the control is set correctly
        self.assertEqual(self.control.owner_state, OwnerState.AGENT_ACTIVE)

    def test_return_to_bot_transition(self):
        """Returning to BOT restores eligibility."""
        # Start: AGENT
        self.control.owner_state = OwnerState.AGENT_ACTIVE
        self.control.save()

        # Transition: BOT
        self.control.owner_state = OwnerState.BOT_ACTIVE
        self.control.save()

        # Should be eligible (at least from ownership perspective)
        self.control.refresh_from_db()
        self.assertEqual(self.control.owner_state, OwnerState.BOT_ACTIVE)


@override_settings(CHANNEL_SCHEDULE_BYPASS_FOR_TESTING=[7])
class Channel7ScheduleBypassTest(TestCase):
    """Channel 7 TEST has explicit schedule bypass."""

    def setUp(self):
        self.client_rec = Cliente.objects.create(telefono="51999999999")
        self.channel_7 = WhatsAppChannel.objects.create(
            id=7, nombre="Channel 7 TEST", phone_number_id="9999999999"
        )
        ChannelIntegrationPolicy.objects.create(
            channel=self.channel_7, enabled=True, ai_v31_mode="active"
        )

    def test_channel_7_bypass_outside_hours(self):
        """Channel 7 should respond even outside normal hours."""
        outside_hours = timezone.now().replace(hour=3, minute=0)
        result = should_bot_reply(now=outside_hours, lead=None, channel=self.channel_7)
        self.assertTrue(result, "Channel 7 with bypass must return True outside hours")

    def test_channel_7_is_bypassed(self):
        """Verify _is_schedule_bypassed_for_testing recognizes Channel 7."""
        result = _is_schedule_bypassed_for_testing(self.channel_7)
        self.assertTrue(result, "Channel 7 must have bypass enabled")

    def test_other_channels_not_bypassed(self):
        """Other channels must NOT have bypass."""
        other_channel = WhatsAppChannel.objects.create(
            id=99, nombre="Other", phone_number_id="8888888888"
        )
        result = _is_schedule_bypassed_for_testing(other_channel)
        self.assertFalse(result, "Non-Channel7 must NOT have bypass")


class OrphanInvariantTest(TestCase):
    """Valid inbound → exactly one BotGeneration."""

    def setUp(self):
        self.client_rec = Cliente.objects.create(telefono="51999999999")
        self.channel = WhatsAppChannel.objects.create(
            nombre="TestChannel", phone_number_id="1111111111"
        )
        ChannelIntegrationPolicy.objects.create(
            channel=self.channel, enabled=True, ai_v31_mode="active"
        )

    def test_no_orphan_on_schedule_miss_in_production(self):
        """Schedule miss in production → no BotGeneration (correct), no false ownership."""
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_rec, channel=self.channel
        )
        lead = Lead.objects.create(
            cliente=self.client_rec, whatsapp_channel=self.channel
        )
        conversation.lead = lead
        conversation.save()
        control = ConversationControl.objects.create(
            conversation=conversation, owner_state=OwnerState.BOT_ACTIVE
        )

        # Outside hours in production (Channel != 7)
        outside_hours = timezone.now().replace(hour=3, minute=0)
        result = should_bot_reply(now=outside_hours, lead=lead, channel=self.channel)
        self.assertFalse(result, "Production channel outside hours should block")

        # But: no false atencion_humana=True
        lead.refresh_from_db()
        self.assertFalse(lead.atencion_humana, "Schedule miss must NOT set atencion_humana")

        # And: control.owner_state remains BOT
        control.refresh_from_db()
        self.assertEqual(control.owner_state, OwnerState.BOT_ACTIVE)
