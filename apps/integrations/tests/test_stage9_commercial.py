from unittest.mock import Mock

from django.test import override_settings

from apps.cotizador.commercial import crear_cotizacion_automatica, guardar_borrador
from apps.cotizador.delivery import queue_revision_whatsapp
from apps.cotizador.models import Cotizacion, CotizacionComercial, RevisionCotizacion, SolicitudCotizacion
from apps.integrations.enums import SyncStatus
from apps.integrations.models import (
    ChannelInboxMapping, ChatwootAccountMapping, ChatwootContactMapping,
    ContactInboxMapping, ConversationMapping, IntegrationOutboxEvent,
)
from apps.integrations.services.commercial_labels import (
    process_commercial_label_event, queue_commercial_label_projection,
)
from apps.integrations.services.state_machine import take_conversation
from apps.integrations.services.generations import finalize_generation, start_generation
from apps.integrations.tests.base import IntegrationTestCase
from apps.whatsapp.domain import enviar_a_cotizar
from apps.whatsapp.models import ConversacionWhatsApp


class Stage9CommercialTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        account = ChatwootAccountMapping.objects.create(
            environment="stage9", account_id="7", active=True, sync_status=SyncStatus.SYNCED
        )
        inbox = ChannelInboxMapping.objects.create(
            channel=self.channel, account=account, inbox_id="9", inbox_identifier="stage9",
            active=True, sync_status=SyncStatus.SYNCED,
        )
        contact = ChatwootContactMapping.objects.create(
            cliente=self.client_record, account=account, contact_id="11", active=True,
            sync_status=SyncStatus.SYNCED,
        )
        source = ContactInboxMapping.objects.create(
            contact=contact, inbox=inbox, source_id="stage9-source", sync_status=SyncStatus.SYNCED
        )
        self.mapping = ConversationMapping.objects.create(
            conversation=self.conversation, contact_inbox=source,
            external_conversation_id="13", active=True, sync_status=SyncStatus.SYNCED,
        )

    def test_mark_for_quote_is_idempotent(self):
        first = enviar_a_cotizar(self.conversation.id, self.user, "especial", ["fotos"])
        second = enviar_a_cotizar(self.conversation.id, self.user, "especial", ["fotos"])
        self.assertEqual(first.id, second.id)
        self.assertEqual(SolicitudCotizacion.objects.count(), 1)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.estado_cotizacion, ConversacionWhatsApp.COTIZACION_PENDIENTE)

    def test_save_draft_does_not_send_or_change_ownership(self):
        solicitud = enviar_a_cotizar(self.conversation.id, self.user, "manual")
        quote, revision = guardar_borrador(
            solicitud, self.user, 650, mensaje_whatsapp="Precio S/ 650"
        )
        self.control.refresh_from_db()
        self.assertEqual(self.control.owner_state, "BOT_ACTIVO")
        self.assertEqual(quote.estado, "borrador")
        self.assertFalse(revision.enviada)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(event_type="send_commercial_quote").count(), 0)

    def test_human_queue_takes_over_and_is_idempotent(self):
        solicitud = enviar_a_cotizar(self.conversation.id, self.user, "manual")
        _quote, revision = guardar_borrador(
            solicitud, self.user, 650, mensaje_whatsapp="Precio S/ 650"
        )
        first, created = queue_revision_whatsapp(revision.id, actor=self.user)
        second, created_again = queue_revision_whatsapp(revision.id, actor=self.user)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.outbox_event_id, second.outbox_event_id)
        self.assertEqual(IntegrationOutboxEvent.objects.filter(event_type="send_commercial_quote").count(), 1)
        self.control.refresh_from_db()
        self.assertEqual(self.control.owner_state, "ASESOR_ACTIVO")

    def test_bot_quote_creates_structure_and_commercial_outbox(self):
        generation = start_generation(self.conversation.id, request_key="stage9-auto")
        technical = Cotizacion.objects.create(
            lead=self.lead, precio_min=400, precio_max=500,
            precio_recomendado=450,
        )
        quote, revision, created = crear_cotizacion_automatica(
            self.conversation, technical, "Precio S/ 500",
            source_key=f"bot-generation:{generation.id}",
        )
        _generation, outbox, published = finalize_generation(
            generation.id, result_text="Precio S/ 500"
        )
        self.assertTrue(created)
        self.assertTrue(published)
        self.assertEqual(quote.origen, "bot")
        self.assertEqual(revision.cotizacion_tecnica, technical)
        self.assertEqual(outbox.event_type, "send_commercial_quote")

    @override_settings(CHATWOOT_COMMERCIAL_LABELS_ENABLED=True)
    def test_projection_preserves_unrelated_labels(self):
        enviar_a_cotizar(self.conversation.id, self.user, "manual")
        event, _ = queue_commercial_label_projection(self.conversation.id)
        client = Mock()
        client.ensure_label.return_value = ({}, False)
        client.get_conversation.return_value = {"labels": ["vip", "cotizado"]}
        result = process_commercial_label_event(event.id, client=client)
        self.assertEqual(result.status, "sent")
        client.set_conversation_labels.assert_called_once_with("13", {"vip", "por-cotizar"})

    @override_settings(CHATWOOT_COMMERCIAL_LABELS_ENABLED=True)
    def test_forced_projection_reconciles_an_already_sent_event(self):
        enviar_a_cotizar(self.conversation.id, self.user, "manual")
        event, _ = queue_commercial_label_projection(self.conversation.id)
        event.status = "sent"
        event.save(update_fields=["status"])
        client = Mock()
        client.ensure_label.return_value = ({}, False)
        client.get_conversation.return_value = {"labels": ["vip", "cotizado"]}

        result = process_commercial_label_event(event.id, client=client, force=True)

        self.assertEqual(result.status, "sent")
        client.set_conversation_labels.assert_called_once_with("13", {"vip", "por-cotizar"})

    def test_manual_label_does_not_create_quote(self):
        self.assertEqual(CotizacionComercial.objects.count(), 0)
        self.assertEqual(RevisionCotizacion.objects.count(), 0)
