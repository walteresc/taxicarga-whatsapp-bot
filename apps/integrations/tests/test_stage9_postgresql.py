from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase

from apps.clientes.models import Cliente
from apps.cotizador.commercial import crear_revision, guardar_borrador
from apps.cotizador.delivery import queue_revision_whatsapp
from apps.cotizador.models import RevisionCotizacion, SolicitudCotizacion
from apps.integrations.models import ConversationControl, IntegrationOutboxEvent
from apps.leads.models import Lead
from apps.whatsapp.domain import enviar_a_cotizar
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only Stage 9 race tests.")
class Stage9PostgreSQLTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user("stage9_pg")
        customer = Cliente.objects.create(telefono="stage9-pg-customer")
        channel = WhatsAppChannel.objects.create(
            nombre="Stage9 PG", phone_number_id="stage9-pg-phone", activo=True
        )
        self.lead = Lead.objects.create(cliente=customer, whatsapp_channel=channel)
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=customer, lead=self.lead, channel=channel
        )
        ConversationControl.objects.create(conversation=self.conversation)

    def _race(self, operation):
        barrier = Barrier(2, timeout=10)
        def run(index):
            close_old_connections()
            try:
                barrier.wait()
                return operation(index)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return [future.result(timeout=20) for future in [
                pool.submit(run, 0), pool.submit(run, 1)
            ]]

    def test_mark_for_quote_simultaneous_creates_one_request(self):
        ids = self._race(lambda _i: enviar_a_cotizar(
            self.conversation.id, self.user, "race"
        ).id)
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(SolicitudCotizacion.objects.count(), 1)

    def test_simultaneous_draft_creates_one_commercial_two_revisions(self):
        request = enviar_a_cotizar(self.conversation.id, self.user, "race")
        quote_ids = self._race(lambda i: guardar_borrador(
            SolicitudCotizacion.objects.get(pk=request.id), self.user, 500 + i,
            source_key=f"pg-draft-{i}", mensaje_whatsapp=f"Precio {500 + i}",
        )[0].id)
        self.assertEqual(len(set(quote_ids)), 1)
        self.assertEqual(RevisionCotizacion.objects.count(), 2)
        self.assertEqual(
            list(RevisionCotizacion.objects.order_by("numero").values_list("numero", flat=True)),
            [1, 2],
        )

    def test_simultaneous_revision_numbers_are_unique(self):
        request = enviar_a_cotizar(self.conversation.id, self.user, "race")
        quote, _revision = guardar_borrador(request, self.user, 500, mensaje_whatsapp="v1")
        numbers = self._race(lambda i: crear_revision(
            quote, self.user, 600 + i, source_key=f"pg-revision-{i}",
            mensaje_whatsapp=f"v{i + 2}",
        ).numero)
        self.assertCountEqual(numbers, [2, 3])

    def test_two_workers_queue_same_revision_once(self):
        request = enviar_a_cotizar(self.conversation.id, self.user, "race")
        _quote, revision = guardar_borrador(request, self.user, 500, mensaje_whatsapp="Precio")
        ids = self._race(lambda _i: str(queue_revision_whatsapp(
            RevisionCotizacion.objects.get(pk=revision.id).id, actor=self.user
        )[0].outbox_event_id))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(event_type="send_commercial_quote").count(), 1)
