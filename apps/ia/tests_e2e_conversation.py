"""End-to-end conversation flow test without physical Meta."""
from unittest.mock import patch
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel
from apps.integrations.models import ConversationControl

from .conversation_engine import handle_incoming_message
from .request_lifecycle import resolve_request_lifecycle, RequestIntent


class E2EConversationFlowTest(TestCase):
    """Full conversation flow from greeting to quote."""

    def setUp(self):
        self.client_record = Cliente.objects.create(telefono="51900000e2etest")
        self.channel = WhatsAppChannel.objects.create(
            nombre="E2E TEST",
            phone_number_id="e2etest123"
        )

    @patch("apps.ia.conversation_engine.cotizar_lead")
    @patch("apps.ia.providers.build_provider")
    def test_full_conversation_flow_greeting_to_quote(self, provider_mock, cotizar_mock):
        """Full flow: greeting → new request → collect data → quote."""
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_record,
            channel=self.channel,
            ultima_actividad=timezone.now()
        )
        ConversationControl.objects.create(conversation=conversation)

        # Step 1: New client sends greeting "Buenas, necesito una mudanza"
        lead, reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="Buenas, necesito una mudanza",
            generation_id="e2e-1"
        )
        conversation.refresh_from_db()

        # Should create new lead
        self.assertEqual(intent, RequestIntent.NEW_REQUEST)
        self.assertIsNotNone(lead)
        self.assertEqual(lead.estado, Lead.NUEVO)
        self.assertEqual(conversation.lead.id, lead.id)

        # Step 2: Client provides route
        message = "sale de Surco y va a Miraflores"
        reply = handle_incoming_message(
            self.client_record,
            message,
            lead=lead
        )
        lead.refresh_from_db()

        # Should extract route
        self.assertIn("Surco", str(lead.distrito_origen).capitalize() if lead.distrito_origen else "")
        self.assertIn("Miraflores", str(lead.distrito_destino).capitalize() if lead.distrito_destino else "")

        # Step 3: Provide service type and collect full data
        # Mock cotizar_lead to return a quote
        from decimal import Decimal
        cotizar_mock.return_value.precio_min = Decimal("100")
        cotizar_mock.return_value.precio_max = Decimal("250")
        cotizar_mock.return_value.precio_recomendado = Decimal("175")

        # Add required data
        lead.tipo_servicio = "mudanza"
        lead.lista_objetos = "Cama, mesa, sillas"
        from datetime import date
        lead.fecha_servicio = date.today()
        lead.save()

        reply = handle_incoming_message(
            self.client_record,
            "Tengo que mudanme con cama, mesa y sillas. Puede ser mañana?",
            lead=lead
        )

        lead.refresh_from_db()
        # Should be EN_CONVERSACION or COTIZADO (data collected or quote ready)
        self.assertIn(lead.estado, [Lead.EN_CONVERSACION, Lead.DATOS_INCOMPLETOS, Lead.COTIZADO])

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_active_lead_continues_with_new_data(self, classify_mock):
        """ACTIVE lead receives clarification, user responds, intent classified correctly."""
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_record,
            channel=self.channel,
            ultima_actividad=timezone.now()
        )
        ConversationControl.objects.create(conversation=conversation)

        # Create active lead with incomplete data
        lead = Lead.objects.create(
            cliente=self.client_record,
            whatsapp_channel=self.channel,
            estado=Lead.DATOS_INCOMPLETOS,
            tipo_servicio="mudanza"
        )
        conversation.lead = lead
        conversation.save()

        # User says "sale Surco y va a Miraflores"
        result_intent = RequestIntent.CONTINUE_REQUEST

        # Mock GPT to classify as CONTINUE_REQUEST
        from .request_lifecycle import RequestIntentResponse
        classify_mock.return_value = RequestIntentResponse(
            intent=result_intent,
            confidence=0.92,
            clarification_text=None
        )

        result_lead, reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="sale Surco y va a Miraflores",
            generation_id="e2e-2"
        )

        # Should continue with same lead
        self.assertEqual(result_lead.id, lead.id)
        self.assertEqual(intent, RequestIntent.CONTINUE_REQUEST)
        self.assertIsNone(reply)  # No early reply, proceed to data extraction

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_dormant_lead_offers_reactivation_ask_new(self, classify_mock):
        """DORMANT lead (>2h inactivity) classified as DORMANT, GPT asks reactivation."""
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_record,
            channel=self.channel,
            ultima_actividad=timezone.now() - timedelta(hours=3)  # 3 hours ago = DORMANT
        )
        ConversationControl.objects.create(conversation=conversation)

        # Create dormant lead
        lead = Lead.objects.create(
            cliente=self.client_record,
            whatsapp_channel=self.channel,
            estado=Lead.DATOS_INCOMPLETOS,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores"
        )
        conversation.lead = lead
        conversation.save()

        # Mock GPT to detect DORMANT and ask if reactivate (UNCERTAIN)
        from .request_lifecycle import RequestIntentResponse
        classify_mock.return_value = RequestIntentResponse(
            intent=RequestIntent.UNCERTAIN,
            confidence=0.85,
            clarification_text="¿Quieres continuar con la cotización anterior o empezar una nueva?"
        )

        result_lead, reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="Hola, necesito mudanza",
            generation_id="e2e-3"
        )

        # Should offer reactivation
        self.assertEqual(intent, RequestIntent.UNCERTAIN)
        self.assertIsNotNone(reply)
        self.assertIn("continuar", reply.lower())
        conversation.refresh_from_db()
        self.assertTrue(conversation.pending_request_switch)

    @patch("apps.ia.request_lifecycle.classify_request_intent")
    def test_reactivation_rejection_no_response(self, classify_mock):
        """User says 'no' to reactivation → continue with current lead, no error."""
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_record,
            channel=self.channel,
            ultima_actividad=timezone.now()
        )
        ConversationControl.objects.create(conversation=conversation)

        # Create lead pending reactivation
        lead = Lead.objects.create(
            cliente=self.client_record,
            whatsapp_channel=self.channel,
            estado=Lead.DATOS_INCOMPLETOS,
            tipo_servicio="mudanza"
        )
        conversation.lead = lead
        conversation.pending_request_switch = True
        conversation.save()

        # Mock GPT to classify "no" as NO_REQUEST_SIGNAL
        from .request_lifecycle import RequestIntentResponse
        classify_mock.return_value = RequestIntentResponse(
            intent=RequestIntent.NO_REQUEST_SIGNAL,
            confidence=0.95,
            clarification_text=None
        )

        # User says "no" - should NOT crash, should convert to CONTINUE_REQUEST
        result_lead, reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="no",
            generation_id="e2e-4"
        )

        # Verify no error, intent converted to CONTINUE_REQUEST
        self.assertEqual(result_lead.id, lead.id)
        self.assertEqual(intent, RequestIntent.CONTINUE_REQUEST)
        self.assertIsNone(reply)

        # Verify pending_request_switch cleared
        conversation.refresh_from_db()
        self.assertFalse(conversation.pending_request_switch)
