"""Test CONTEXTUAL ANSWER priority over lifecycle classification."""
from django.test import TestCase
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp, MensajeWhatsApp
from apps.leads.models import Lead
from apps.ia.request_lifecycle import resolve_request_lifecycle, RequestIntent


class ContextualAnswerPriorityTest(TestCase):
    """Test that direct answers to current questions have priority over lifecycle."""

    def setUp(self):
        self.client = Cliente.objects.create(telefono="51999999999")
        self.channel = WhatsAppChannel.objects.create(nombre="TEST", phone_number_id="123")

    def test_route_answer_to_route_question(self):
        """
        SCENARIO:
        1. Client: "Hola, necesito un presupuesto para una mudanza"
        2. Bot creates lead, asks: "¿Cuál es el distrito de partida y llegada?"
        3. Client: "la molina a san luis"

        EXPECTED:
        - Request intent = CONTINUE_REQUEST
        - NO reactivation prompt
        - origin = La Molina, destination = San Luis (in response processing)
        """
        # Create conversation and lead
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel,
        )
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            tipo_servicio="mudanza",
            estado=Lead.EN_CONVERSACION,
        )
        conversation.lead = lead
        conversation.save()

        # Simulate bot asking route question
        bot_question = MensajeWhatsApp.objects.create(
            conversacion=conversation,
            direccion="SALIENTE",
            origen="bot",
            tipo="texto",
            contenido="¿Cuál es el distrito de partida y llegada?",
        )

        # Client answers with clear route
        client_message = "la molina a san luis"

        # Resolve lifecycle
        new_lead, early_reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message=client_message,
            generation_id="test-gen-1",
        )

        # Assertions
        self.assertEqual(intent, RequestIntent.CONTINUE_REQUEST)
        self.assertIsNone(early_reply, "Should NOT prompt reactivation for contextual answer")
        self.assertEqual(new_lead.id, lead.id, "Should stay with current lead")

    def test_floor_answer_to_floor_question(self):
        """Client answers floor question with floor numbers."""
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel,
        )
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            tipo_servicio="mudanza",
            estado=Lead.EN_CONVERSACION,
        )
        conversation.lead = lead
        conversation.save()

        # Bot asks floor question
        MensajeWhatsApp.objects.create(
            conversacion=conversation,
            direccion="SALIENTE",
            origen="bot",
            tipo="texto",
            contenido="¿De qué piso sale y a qué piso llega?",
        )

        # Client answers with floors
        new_lead, early_reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="tercero al primero",
            generation_id="test-gen-2",
        )

        self.assertEqual(intent, RequestIntent.CONTINUE_REQUEST)
        self.assertIsNone(early_reply)
        self.assertEqual(new_lead.id, lead.id)

    def test_yes_no_answer_to_access_question(self):
        """Client answers elevator/access question with yes/no."""
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel,
        )
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            tipo_servicio="mudanza",
            estado=Lead.EN_CONVERSACION,
        )
        conversation.lead = lead
        conversation.save()

        # Bot asks about elevator
        MensajeWhatsApp.objects.create(
            conversacion=conversation,
            direccion="SALIENTE",
            origen="bot",
            tipo="texto",
            contenido="¿En origen hay ascensor?",
        )

        # Client answers no
        new_lead, early_reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="no",
            generation_id="test-gen-3",
        )

        self.assertEqual(intent, RequestIntent.CONTINUE_REQUEST)
        self.assertIsNone(early_reply)
        self.assertEqual(new_lead.id, lead.id)

    def test_items_answer_to_items_question(self):
        """Client describes items in response to 'what things' question."""
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel,
        )
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            tipo_servicio="mudanza",
            estado=Lead.EN_CONVERSACION,
        )
        conversation.lead = lead
        conversation.save()

        # Bot asks what items
        MensajeWhatsApp.objects.create(
            conversacion=conversation,
            direccion="SALIENTE",
            origen="bot",
            tipo="texto",
            contenido="¿Qué cosas llevarías?",
        )

        # Client lists items
        new_lead, early_reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="refrigeradora, cama y 10 cajas",
            generation_id="test-gen-4",
        )

        self.assertEqual(intent, RequestIntent.CONTINUE_REQUEST)
        self.assertIsNone(early_reply)
        self.assertEqual(new_lead.id, lead.id)

    def test_route_answer_with_typo(self):
        """
        EXACT CASE:
        Bot: "¿Cuál es el distrito de partida y llegada?"
        User: "de surquillo a asn luis"

        Typo in "asn luis" (should be "san luis"), but message structure
        is STILL a route answer attempt.

        EXPECTED: CONTINUE_REQUEST, no reactivation prompt.
        """
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel,
        )
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            tipo_servicio="mudanza",
            estado=Lead.EN_CONVERSACION,
        )
        conversation.lead = lead
        conversation.save()

        # Bot asks route question
        MensajeWhatsApp.objects.create(
            conversacion=conversation,
            direccion="SALIENTE",
            origen="bot",
            tipo="texto",
            contenido="¿Cuál es el distrito de partida y llegada?",
        )

        # Client answers with typo
        new_lead, early_reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="de surquillo a asn luis",
            generation_id="test-gen-typo",
        )

        self.assertEqual(intent, RequestIntent.CONTINUE_REQUEST,
                        "Typo in location shouldn't prevent contextual route answer")
        self.assertIsNone(early_reply, "Should NOT prompt reactivation for route answer with typo")
        self.assertEqual(new_lead.id, lead.id)

    def test_no_last_question_falls_back_to_lifecycle(self):
        """When no recent bot message, fallback to lifecycle classification."""
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client,
            channel=self.channel,
        )
        lead = Lead.objects.create(
            cliente=self.client,
            whatsapp_channel=self.channel,
            tipo_servicio="mudanza",
            estado=Lead.EN_CONVERSACION,
        )
        conversation.lead = lead
        conversation.save()
        # NO bot message created

        # Client sends ambiguous message
        new_lead, early_reply, intent = resolve_request_lifecycle(
            conversation_id=conversation.id,
            message="necesito otra mudanza",
            generation_id="test-gen-5",
        )

        # Should fall back to lifecycle classification (will be NEW_REQUEST for "otra")
        # or ask clarification based on AI
        self.assertIn(intent, {RequestIntent.NEW_REQUEST, RequestIntent.UNCERTAIN})
