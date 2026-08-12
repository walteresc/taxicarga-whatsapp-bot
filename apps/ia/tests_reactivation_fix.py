"""Tests for reactivation rejection and historical match priority fix."""
from unittest.mock import patch
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel
from apps.integrations.models import ConversationControl

from .request_lifecycle import (
    RequestIntent,
    resolve_request_lifecycle,
)


class ReactivationRejectionTests(TestCase):
    """Test handling of user rejection to reactivation prompt."""

    def setUp(self):
        self.client = Cliente.objects.create(telefono="51900000reactivate")
        self.channel = WhatsAppChannel.objects.create(
            nombre="TEST reactivation",
            phone_number_id="reactivate123"
        )

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_reactivation_rejection_clears_pending_switch(self, classify_mock):
        """When user says 'no' to reactivation prompt, clear pending_request_switch."""
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel,
            ultima_actividad=timezone.now()
        )
        ConversationControl.objects.create(conversation=conversation)

        # Setup: Active lead with pending reactivation question
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            estado=Lead.DATOS_INCOMPLETOS
        )
        conversation.lead = lead
        conversation.pending_request_switch = True
        conversation.save()

        # Mock GPT to say "no" = NO_REQUEST_SIGNAL
        classify_mock.return_value.intent = RequestIntent.NO_REQUEST_SIGNAL
        classify_mock.return_value.confidence = 0.95
        classify_mock.return_value.clarification_text = None

        # Process user's "no" response
        result_lead, reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="no",
            generation_id="test-reject"
        )

        # Verify: pending_request_switch was cleared
        conversation.refresh_from_db()
        self.assertFalse(conversation.pending_request_switch)

        # Verify: lead unchanged (no new lead created)
        self.assertEqual(result_lead.id, lead.id)

        # Verify: intent converted to CONTINUE_REQUEST (proceed with current lead)
        self.assertEqual(intent, RequestIntent.CONTINUE_REQUEST)

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_active_new_lead_not_replaced_by_route_match(self, classify_mock):
        """When new lead is ACTIVE and user provides historical route, keep new lead."""
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel,
            ultima_actividad=timezone.now()
        )
        ConversationControl.objects.create(conversation=conversation)

        # New lead was just created for current request
        new_lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            estado=Lead.DATOS_INCOMPLETOS
        )
        conversation.lead = new_lead
        conversation.save()

        # Create historical lead with same route (Surco→Miraflores)
        historical_lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            estado=Lead.PERDIDO,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores"
        )

        # Mock: user says "sale surco y va a miraflores" = CONTINUE_REQUEST
        classify_mock.return_value.intent = RequestIntent.CONTINUE_REQUEST
        classify_mock.return_value.confidence = 0.88
        classify_mock.return_value.clarification_text = None

        result_lead, reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="sale surco y va a miraflores",
            generation_id="test-route"
        )

        # Verify: new lead is maintained (not replaced by historical)
        self.assertEqual(result_lead.id, new_lead.id)
        self.assertNotEqual(result_lead.id, historical_lead.id)
        self.assertEqual(intent, RequestIntent.CONTINUE_REQUEST)

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_reactivation_acceptance_when_explicit(self, classify_mock):
        """Only offer reactivation if user explicitly requests it (future GPT enhancement)."""
        # This test documents the expected behavior when GPT detects explicit
        # intention like "continue the moving I quoted yesterday"
        # For now, just verify that CONTINUE_REQUEST doesn't trigger reactivation
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel,
            ultima_actividad=timezone.now()
        )
        ConversationControl.objects.create(conversation=conversation)

        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            estado=Lead.DATOS_INCOMPLETOS
        )
        conversation.lead = lead
        conversation.pending_request_switch = True
        conversation.save()

        classify_mock.return_value.intent = RequestIntent.CONTINUE_REQUEST
        classify_mock.return_value.confidence = 0.92
        classify_mock.return_value.clarification_text = None

        result_lead, reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="si, quiero continuar",
            generation_id="test-accept"
        )

        # pending_request_switch should be cleared (handled in main logic)
        conversation.refresh_from_db()
        self.assertFalse(conversation.pending_request_switch)
