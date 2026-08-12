"""Tests for structured request lifecycle status (ACTIVE/DORMANT/CLOSED)."""
from unittest.mock import patch
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel

from .request_lifecycle import (
    RequestIntent,
    RequestLifecycleStatus,
    resolve_request_lifecycle,
    _determine_lifecycle_status,
    INACTIVITY_THRESHOLD,
)


class LifecycleStatusTests(TestCase):
    def setUp(self):
        self.client = Cliente.objects.create(telefono="51900000111")
        self.channel = WhatsAppChannel.objects.create(nombre="TEST lifecycle status", phone_number_id="lifecycle")
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel,
            ultima_actividad=timezone.now()
        )

    def test_null_lead_is_active(self):
        """lead=null should be ACTIVE (ready to create new request)."""
        status, lead_id = _determine_lifecycle_status(None, self.conversation)
        self.assertEqual(status, RequestLifecycleStatus.ACTIVE)
        self.assertIsNone(lead_id)

    def test_closed_lead_is_closed(self):
        """Lead in CERRADO state should be CLOSED."""
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            estado=Lead.CERRADO
        )
        self.conversation.lead = lead
        self.conversation.save()

        status, lead_id = _determine_lifecycle_status(lead, self.conversation)
        self.assertEqual(status, RequestLifecycleStatus.CLOSED)
        self.assertEqual(lead_id, lead.id)

    def test_lost_lead_is_closed(self):
        """Lead in PERDIDO state should be CLOSED."""
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            estado=Lead.PERDIDO
        )
        self.conversation.lead = lead
        self.conversation.save()

        status, lead_id = _determine_lifecycle_status(lead, self.conversation)
        self.assertEqual(status, RequestLifecycleStatus.CLOSED)

    def test_recent_lead_is_active(self):
        """Lead with recent activity should be ACTIVE."""
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            estado=Lead.DATOS_INCOMPLETOS
        )
        self.conversation.lead = lead
        self.conversation.ultima_actividad = timezone.now()
        self.conversation.save()

        status, lead_id = _determine_lifecycle_status(lead, self.conversation)
        self.assertEqual(status, RequestLifecycleStatus.ACTIVE)

    def test_inactive_lead_is_dormant(self):
        """Lead without activity > INACTIVITY_THRESHOLD should be DORMANT."""
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            estado=Lead.DATOS_INCOMPLETOS
        )
        self.conversation.lead = lead
        self.conversation.ultima_actividad = timezone.now() - INACTIVITY_THRESHOLD - timedelta(minutes=1)
        self.conversation.save()

        status, lead_id = _determine_lifecycle_status(lead, self.conversation)
        self.assertEqual(status, RequestLifecycleStatus.DORMANT)


class RequestLifecycleIntegrationTests(TestCase):
    def setUp(self):
        self.client = Cliente.objects.create(telefono="51900000222")
        self.channel = WhatsAppChannel.objects.create(nombre="TEST lifecycle", phone_number_id="lifecycle2")
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel
        )

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_null_lead_new_request_clean_lead(self, classify_mock):
        """conversation.lead=null + clear service request → NEW_REQUEST, create clean Lead."""
        classify_mock.return_value.intent = RequestIntent.NEW_REQUEST
        classify_mock.return_value.confidence = 0.95
        classify_mock.return_value.clarification_text = None

        self.conversation.lead = None
        self.conversation.save()

        new_lead, reply, intent = resolve_request_lifecycle(
            conversation_id=self.conversation.id,
            message="Buenas, necesito una mudanza",
            generation_id="g1"
        )

        self.assertIsNotNone(new_lead)
        self.assertIsNone(reply)
        self.assertEqual(intent, RequestIntent.NEW_REQUEST)
        self.assertTrue(new_lead.tipo_servicio == "" or new_lead.tipo_servicio is None)
        self.assertFalse(new_lead.ubicaciones.exists())

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_dormant_lead_clear_new_request(self, classify_mock):
        """lead=DORMANT + clear new request → NEW_REQUEST, no historical contamination."""
        old_lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            estado=Lead.DATOS_INCOMPLETOS,
            tipo_servicio="mudanza",
            distrito_origen="Surco"
        )
        self.conversation.lead = old_lead
        self.conversation.ultima_actividad = timezone.now() - INACTIVITY_THRESHOLD - timedelta(hours=1)
        self.conversation.save()

        classify_mock.return_value.intent = RequestIntent.NEW_REQUEST
        classify_mock.return_value.confidence = 0.92
        classify_mock.return_value.clarification_text = None

        new_lead, reply, intent = resolve_request_lifecycle(
            conversation_id=self.conversation.id,
            message="Hola, otra vez necesito mudanza",
            generation_id="g2"
        )

        self.assertIsNotNone(new_lead)
        self.assertNotEqual(new_lead.id, old_lead.id)
        self.assertEqual(intent, RequestIntent.NEW_REQUEST)

        # Verify historical lead not contaminated
        old_lead.refresh_from_db()
        self.assertEqual(old_lead.estado, Lead.PERDIDO)
        self.assertEqual(old_lead.tipo_servicio, "mudanza")

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_active_lead_continue_request(self, classify_mock):
        """lead=ACTIVE + continuation message → CONTINUE_REQUEST, no new lead."""
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            estado=Lead.DATOS_INCOMPLETOS
        )
        self.conversation.lead = lead
        self.conversation.ultima_actividad = timezone.now()
        self.conversation.save()

        classify_mock.return_value.intent = RequestIntent.CONTINUE_REQUEST
        classify_mock.return_value.confidence = 0.88
        classify_mock.return_value.clarification_text = None

        result_lead, reply, intent = resolve_request_lifecycle(
            conversation_id=self.conversation.id,
            message="Sí, contínua con la anterior",
            generation_id="g3"
        )

        self.assertEqual(result_lead.id, lead.id)
        self.assertIsNone(reply)
        self.assertEqual(intent, RequestIntent.CONTINUE_REQUEST)

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_active_lead_ambiguous_asks_clarification(self, classify_mock):
        """lead=ACTIVE + ambiguous message → UNCERTAIN, ask for clarification."""
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            estado=Lead.DATOS_INCOMPLETOS
        )
        self.conversation.lead = lead
        self.conversation.ultima_actividad = timezone.now()
        self.conversation.save()

        classify_mock.return_value.intent = RequestIntent.UNCERTAIN
        classify_mock.return_value.confidence = 0.70
        classify_mock.return_value.clarification_text = "¿Deseas continuar o una nueva solicitud?"

        result_lead, reply, intent = resolve_request_lifecycle(
            conversation_id=self.conversation.id,
            message="Necesito cotizar",
            generation_id="g4"
        )

        self.assertEqual(result_lead.id, lead.id)
        self.assertIn("nueva", reply.lower())
        self.assertEqual(intent, RequestIntent.UNCERTAIN)

        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.pending_request_switch)
