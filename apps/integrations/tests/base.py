from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.clientes.models import Cliente
from apps.integrations.models import ConversationControl
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel


class IntegrationTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="advisor_one", password="test")
        self.other_user = get_user_model().objects.create_user(username="advisor_two", password="test")
        self.client_record = Cliente.objects.create(telefono="test-customer-001")
        self.channel = WhatsAppChannel.objects.create(
            nombre="Sandbox Uno", phone_number_id="sandbox-phone-id-1", activo=True
        )
        self.lead = Lead.objects.create(cliente=self.client_record, whatsapp_channel=self.channel)
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_record, lead=self.lead, channel=self.channel
        )
        self.control = ConversationControl.objects.create(conversation=self.conversation)

    def create_second_channel_conversation(self):
        channel = WhatsAppChannel.objects.create(
            nombre="Sandbox Dos", phone_number_id="sandbox-phone-id-2", activo=True
        )
        lead = Lead.objects.create(cliente=self.client_record, whatsapp_channel=channel)
        conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_record, lead=lead, channel=channel
        )
        ConversationControl.objects.create(conversation=conversation)
        return channel, conversation
