from django.test import TestCase

from apps.clientes.models import Cliente
from apps.cotizador.models import SolicitudCotizacion
from apps.integrations.enums import OwnerState
from apps.integrations.models import ConversationControl
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp

from ..adapters.chatwoot import ChatwootV4Adapter
from ..adapters.crm import CRMV4Adapter
from ..domain.state import Access
from ..models import BotConversationState
from ..repositories.state import DjangoBotStateRepository
from ..services.conversation_service import ConversationService
from ..services.persistent_conversation_service import PersistentConversationService
from .fakes import ScriptedAgent, output


class PersistentIntegrationTests(TestCase):
    def setUp(self):
        client = Cliente.objects.create(telefono="51999000003")
        self.lead = Lead.objects.create(cliente=client)
        self.conversation = ConversacionWhatsApp.objects.create(cliente=client, lead=self.lead)
        self.control = ConversationControl.objects.create(conversation=self.conversation)
        self.key = f"whatsapp:{self.conversation.pk}"

    def service(self, scripted_output):
        return PersistentConversationService(
            ConversationService(ScriptedAgent([scripted_output])),
            DjangoBotStateRepository(),
            crm_adapter=CRMV4Adapter(),
            chatwoot_adapter=ChatwootV4Adapter(),
        )

    def turn(self, message, scripted_output):
        return self.service(scripted_output).process_turn(
            conversation_key=self.key,
            conversation=self.conversation,
            lead=self.lead,
            customer_message=message,
        ).turn

    def test_persist_reload_continue_across_restarts(self):
        self.turn("quiero una mudanza", output())
        self.turn("de San Isidro a Miraflores", output(updates={"origin_district": "San Isidro", "destination_district": "Miraflores"}))
        floor_origin = self.turn("primer piso", output(updates={"origin_floor": 1}))
        self.assertEqual(floor_origin.state.origin_district, "San Isidro")
        self.turn("segundo piso", output(updates={"destination_floor": 2}))
        self.turn("escaleras", output(updates={"destination_access": "escaleras"}))
        final = self.turn("una cama", output(updates={"items": ["1 cama"]}, reply="Datos listos para cotizar."))
        self.assertTrue(final.ready_to_quote)
        self.assertEqual(final.state.origin_access, Access.NOT_APPLICABLE)
        self.assertEqual(SolicitudCotizacion.objects.get(lead=self.lead).datos_faltantes, [])

    def test_takeover_blocks_then_return_continues_existing_state(self):
        self.turn("de San Isidro a Miraflores", output(updates={"origin_district": "San Isidro", "destination_district": "Miraflores"}))
        self.control.owner_state = OwnerState.AGENT_ACTIVE
        self.control.save(update_fields=["owner_state"])
        blocked_agent = ScriptedAgent([])
        blocked_service = PersistentConversationService(
            ConversationService(blocked_agent), DjangoBotStateRepository(), chatwoot_adapter=ChatwootV4Adapter()
        )
        blocked = blocked_service.process_turn(
            conversation_key=self.key, conversation=self.conversation, customer_message="primer piso"
        ).turn
        self.assertTrue(blocked.suppressed)
        self.assertEqual(blocked_agent.calls, 0)
        self.control.owner_state = OwnerState.BOT_ACTIVE
        self.control.save(update_fields=["owner_state"])
        resumed = self.turn("primer piso", output(updates={"origin_floor": 1}))
        self.assertEqual(resumed.state.origin_district, "San Isidro")
        self.assertEqual(resumed.state.destination_district, "Miraflores")
        self.assertEqual(resumed.state.origin_floor, 1)

    def test_time_alone_does_not_discard_collecting_state(self):
        # Verificar que tiempo NO descarta estado válido sin NEW_QUOTE explícito
        # Cliente con datos válidos hace 7 horas continúa → datos preservados
        from django.utils import timezone
        from datetime import timedelta
        from django.db import connection

        old_time = timezone.now() - timedelta(hours=7)
        self.turn("de Surco a Miraflores", output(updates={"origin_district": "Surco", "destination_district": "Miraflores"}))

        # Manipular updated_at para simular 7 horas de inactividad
        state_model = BotConversationState.objects.get(conversation_key=self.key)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE whatsapp_bot_v4_botconversationstate SET updated_at = %s WHERE id = %s",
                [old_time, state_model.id]
            )

        # Cliente continúa después de 7 horas
        result = self.turn("necesito otra mudanza", output(
            reply="OK, para la nueva mudanza dime los detalles"
        ))

        # Datos originales DEBEN preservarse (no hay NEW_QUOTE)
        self.assertEqual(result.state.origin_district, "Surco")
        self.assertEqual(result.state.destination_district, "Miraflores")
        # Nuevo mensaje procesado con contexto anterior
        self.assertEqual(result.llm_calls, 1)

