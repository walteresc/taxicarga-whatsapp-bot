from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import IntegrityError, close_old_connections, connection, connections
from django.test import TransactionTestCase

from apps.clientes.models import Cliente
from apps.integrations.enums import Provider
from apps.integrations.models import ExternalMessageMapping
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only Chatwoot race test.")
class ChatwootMappingPostgreSQLTests(TransactionTestCase):
    def setUp(self):
        cliente = Cliente.objects.create(telefono="pg-stage5-test")
        channel = WhatsAppChannel.objects.create(
            nombre="PG Stage 5", phone_number_id="pg-stage5-no-meta", activo=False
        )
        conversation = ConversacionWhatsApp.objects.create(cliente=cliente, channel=channel)
        self.message = MensajeWhatsApp.objects.create(
            conversacion=conversation,
            direccion="entrante",
            origen="cliente",
            contenido="PG race test",
        )

    def test_two_workers_create_only_one_pending_mapping(self):
        barrier = Barrier(2, timeout=10)

        def create_mapping(_index):
            close_old_connections()
            try:
                barrier.wait()
                try:
                    ExternalMessageMapping.objects.create(
                        provider=Provider.CHATWOOT,
                        account_scope="1",
                        whatsapp_message_id=self.message.id,
                    )
                    return "created"
                except IntegrityError:
                    return "duplicate"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [future.result(timeout=20) for future in (
                executor.submit(create_mapping, 0),
                executor.submit(create_mapping, 1),
            )]

        self.assertCountEqual(results, ["created", "duplicate"])
        self.assertEqual(ExternalMessageMapping.objects.count(), 1)
