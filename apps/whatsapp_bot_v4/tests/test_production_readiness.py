"""Pre-production integration tests."""

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp, WhatsAppChannel
from apps.whatsapp_bot_v4.models import BotConversationState, ConversationOwnership, V4ChannelRoute
from apps.whatsapp_bot_v4.repositories.state import DjangoBotStateRepository
from apps.whatsapp_bot_v4.services.conversation_service import ConversationService
from apps.whatsapp_bot_v4.services.persistent_conversation_service import PersistentConversationService
from apps.whatsapp_bot_v4.services.meta_webhook_service import MetaWebhookV4Service
from apps.whatsapp_bot_v4.tests.fakes import ScriptedAgent, output
from apps.whatsapp_bot_v4.tests.meta_fakes import FakeMetaAdapter, RecordingChatwoot


class ProductionReadinessTests(TestCase):
    """Pre-production integration tests"""

    def setUp(self):
        self.channel = WhatsAppChannel.objects.create(
            nombre="Prod Test Channel",
            phone_number_id="test-prod-channel",
            activo=True
        )
        V4ChannelRoute.objects.create(channel=self.channel, enabled=True)
        self.repo = DjangoBotStateRepository()

    def build_service(self, outputs):
        agent = ScriptedAgent(outputs)
        meta = FakeMetaAdapter()
        chatwoot = RecordingChatwoot()
        service = MetaWebhookV4Service(
            meta_adapter=meta,
            persistent_service=PersistentConversationService(
                ConversationService(agent),
                self.repo,
                chatwoot_adapter=chatwoot,
            ),
            chatwoot_adapter=chatwoot,
        )
        return service, agent, meta, chatwoot

    def create_quoted_conversation(self, price=3500.00):
        """Create QUOTED conversation"""
        cliente = Cliente.objects.create(telefono="51999000001")
        lead = Lead.objects.create(cliente=cliente, whatsapp_channel=self.channel)
        conversation = ConversacionWhatsApp.objects.create(
            cliente=cliente, lead=lead, channel=self.channel
        )
        BotConversationState.objects.create(
            conversation_key=f"whatsapp:{conversation.pk}",
            status="quoted",
            quote_price=price,
            state_data={
                "origin_district": "San Isidro",
                "destination_district": "Miraflores",
                "origin_floor": 2,
                "destination_floor": 4,
                "items": ["cama"],
            },
        )
        ConversationOwnership.objects.create(conversation=conversation)
        return conversation

    def test_01_quoted_mode_price_communication(self):
        """Cliente pregunta precio en QUOTED → obtiene precio"""
        service, agent, meta, _ = self.build_service([
            output(reply="Tu presupuesto actual es S/ 3500.00"),
        ])
        conversation = self.create_quoted_conversation(price=3500.00)

        result = service.process_payload({
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "metadata": {"phone_number_id": "test-prod-channel"},
                        "messages": [{
                            "from": "51999000001",
                            "id": "wamid.test.01",
                            "timestamp": str(int(timezone.now().timestamp())),
                            "type": "text",
                            "text": {"body": "¿cuánto cuesta?"},
                        }],
                    },
                }],
            }],
        })

        self.assertEqual(result.status, "sent")
        self.assertIn("3500", meta.sent[0][1].text)

    def test_02_advisor_takeover(self):
        """Asesor entra → bot se silencia"""
        service, agent, meta, chatwoot = self.build_service([
            output(reply="Hola"),
        ])
        conversation = self.create_quoted_conversation()

        # Simular: CRM llama transfer_to_advisor (via Chatwoot mock)
        chatwoot.allowed = False

        result = service.process_payload({
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "metadata": {"phone_number_id": "test-prod-channel"},
                        "messages": [{
                            "from": "51999000001",
                            "id": "wamid.test.02",
                            "timestamp": str(int(timezone.now().timestamp())),
                            "type": "text",
                            "text": {"body": "hola"},
                        }],
                    },
                }],
            }],
        })

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(len(meta.sent), 0)

    def test_03_return_to_bot(self):
        """Asesor devuelve control → bot reactiva"""
        service, agent, meta, chatwoot = self.build_service([
            output(reply="¿En qué te puedo ayudar?"),
        ])
        conversation = self.create_quoted_conversation()

        # Simular: CRM llama return_to_bot
        chatwoot.allowed = True

        result = service.process_payload({
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "metadata": {"phone_number_id": "test-prod-channel"},
                        "messages": [{
                            "from": "51999000001",
                            "id": "wamid.test.03",
                            "timestamp": str(int(timezone.now().timestamp())),
                            "type": "text",
                            "text": {"body": "hola"},
                        }],
                    },
                }],
            }],
        })

        self.assertEqual(result.status, "sent")

    def test_04_timeout_auto_return(self):
        """Asesor inactivo 15+ min → bot retorna automático"""
        service, agent, meta, chatwoot = self.build_service([
            output(reply="¿En qué te puedo ayudar?"),
        ])
        conversation = self.create_quoted_conversation()

        # Setup: Advisor, but inactive
        ownership = ConversationOwnership.objects.get(conversation=conversation)
        ownership.owner_type = ConversationOwnership.OWNER_ADVISOR
        ownership.control_mode = ConversationOwnership.MODE_AUTOMATIC
        ownership.last_human_message_at = timezone.now() - timedelta(minutes=16)
        ownership.save()

        # Chatwoot says allowed now (simula que el asesor se fue)
        chatwoot.allowed = True

        result = service.process_payload({
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "metadata": {"phone_number_id": "test-prod-channel"},
                        "messages": [{
                            "from": "51999000001",
                            "id": "wamid.test.04",
                            "timestamp": str(int(timezone.now().timestamp())),
                            "type": "text",
                            "text": {"body": "hola"},
                        }],
                    },
                }],
            }],
        })

        # Bot debería responder (timeout pasó)
        self.assertEqual(result.status, "sent")

    def test_05_conversation_closed(self):
        """Conversación cerrada → webhook ignora"""
        service, agent, meta, chatwoot = self.build_service([
            output(reply="Hola"),  # Para la nueva conversación que se crea
        ])
        conversation = self.create_quoted_conversation()
        conversation.estado_atencion = ConversacionWhatsApp.ATENCION_CERRADA
        conversation.save()

        result = service.process_payload({
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "metadata": {"phone_number_id": "test-prod-channel"},
                        "messages": [{
                            "from": "51999000001",
                            "id": "wamid.test.05",
                            "timestamp": str(int(timezone.now().timestamp())),
                            "type": "text",
                            "text": {"body": "hola"},
                        }],
                    },
                }],
            }],
        })

        # Debería crear nueva conversación, no processar la cerrada
        self.assertEqual(result.status, "sent")
        # 2 conversaciones: original (cerrada) + nueva
        self.assertEqual(
            ConversacionWhatsApp.objects.filter(cliente__telefono="51999000001").count(),
            2
        )

