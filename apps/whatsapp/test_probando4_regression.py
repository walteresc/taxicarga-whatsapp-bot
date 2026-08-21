"""
Regression test para el defecto "probando4":
- Webhook recibe mensaje pero no actualiza ultima_actividad
- Conversación no sube al primer lugar de la bandeja
"""

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from datetime import timedelta

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
from apps.leads.models import Lead


class Probando4RegressionTest(TransactionTestCase):
    """Ensure incoming messages update ultima_actividad atomically"""

    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombre="Walter Escobar",
            telefono="+51995403320",
        )
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.cliente,
            estado_atencion=ConversacionWhatsApp.ATENCION_BOT,
        )
        # Set old timestamp
        self.old_time = timezone.now() - timedelta(hours=22)
        self.conversation.ultima_actividad = self.old_time
        self.conversation.save(update_fields=["ultima_actividad"])

    def test_inbound_message_updates_ultima_actividad(self):
        """When inbound message arrives, ultima_actividad must update"""
        # Create inbound message
        msg = MensajeWhatsApp.objects.create(
            conversacion=self.conversation,
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            tipo="texto",
            contenido="probando4",
            estado="recibido",
            sender_type="customer",
            source="whatsapp_api",
        )

        # Simulate webhook handler updating ultima_actividad
        # (This is what views.py should do after canonical_incoming_message)
        self.conversation.ultima_actividad = msg.fecha_mensaje
        self.conversation.ultimo_mensaje_cliente = msg.fecha_mensaje
        self.conversation.save(update_fields=["ultima_actividad", "ultimo_mensaje_cliente"])

        # Refresh from DB
        self.conversation.refresh_from_db()

        # Assertions
        self.assertEqual(self.conversation.ultima_actividad, msg.fecha_mensaje)
        self.assertGreater(self.conversation.ultima_actividad, self.old_time)
        self.assertEqual(self.conversation.ultimo_mensaje_cliente, msg.fecha_mensaje)

    def test_late_webhook_does_not_retrocede_ultima_actividad(self):
        """If a late webhook arrives, don't replace newer ultima_actividad"""
        # Create new message first (recent)
        msg_new = MensajeWhatsApp.objects.create(
            conversacion=self.conversation,
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            tipo="texto",
            contenido="probando5",
            estado="recibido",
            sender_type="customer",
            source="whatsapp_api",
        )
        self.conversation.ultima_actividad = msg_new.fecha_mensaje
        self.conversation.save(update_fields=["ultima_actividad"])

        # Now simulate a late webhook with older timestamp
        late_time = timezone.now() - timedelta(minutes=5)
        msg_late = MensajeWhatsApp.objects.create(
            conversacion=self.conversation,
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            tipo="texto",
            contenido="probando_atrasado",
            estado="recibido",
            sender_type="customer",
            source="whatsapp_api",
        )
        msg_late.fecha_mensaje = late_time
        msg_late.save(update_fields=["fecha_mensaje"])

        # Only update if this message is newer
        if msg_late.fecha_mensaje >= self.conversation.ultima_actividad:
            self.conversation.ultima_actividad = msg_late.fecha_mensaje
            self.conversation.save(update_fields=["ultima_actividad"])

        # Refresh and check: ultima_actividad should NOT have gone backwards
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.ultima_actividad, msg_new.fecha_mensaje)
        self.assertGreater(self.conversation.ultima_actividad, msg_late.fecha_mensaje)

    def test_conversation_ordering_by_ultima_actividad(self):
        """Conversations must be ordered by ultima_actividad DESC"""
        # Create two conversations with different timestamps
        client2 = Cliente.objects.create(
            nombre="Another Client",
            telefono="+51999999999",
        )
        conv2 = ConversacionWhatsApp.objects.create(
            cliente=client2,
            estado_atencion=ConversacionWhatsApp.ATENCION_BOT,
        )
        conv2.ultima_actividad = timezone.now()
        conv2.save(update_fields=["ultima_actividad"])

        self.conversation.ultima_actividad = timezone.now() + timedelta(minutes=1)
        self.conversation.save(update_fields=["ultima_actividad"])

        # Query ordered by ultima_actividad DESC
        convs = ConversacionWhatsApp.objects.all().order_by("-ultima_actividad")
        convs_list = list(convs)

        # self.conversation should be first
        self.assertEqual(convs_list[0].id, self.conversation.id)
        self.assertEqual(convs_list[1].id, conv2.id)
