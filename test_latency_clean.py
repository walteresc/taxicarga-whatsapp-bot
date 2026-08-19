#!/usr/bin/env python
"""
Clean latency test: QUOTED vs COLLECTING modes
Logs latency metrics to report
"""
import os, django, logging, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Setup logging to capture INFO level
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s',
)

from django.db import transaction
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp, MensajeWhatsApp, Cliente
from apps.leads.models import Lead
from apps.whatsapp_bot_v4.models import BotConversationState
from apps.whatsapp_bot_v4.services.meta_webhook_service import MetaWebhookV4Service
from apps.whatsapp_bot_v4.services.persistent_conversation_service import PersistentConversationService
from apps.whatsapp_bot_v4.services.conversation_service import ConversationService
from apps.whatsapp_bot_v4.adapters.crm import CRMV4Adapter
from apps.whatsapp_bot_v4.repositories.state import DjangoBotStateRepository
from apps.whatsapp_bot_v4.tests.meta_fakes import FakeMetaAdapter, RecordingChatwoot
from apps.whatsapp_bot_v4.tests.fakes import ScriptedAgent, output

def meta_payload(text, phone_number_id, customer, wamid):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": phone_number_id},
            "messages": [{
                "from": customer,
                "id": wamid,
                "timestamp": "1786665600",
                "type": "text",
                "text": {"body": text},
            }],
        }}]}],
    }

print("\n" + "="*70)
print("LATENCY DIAGNOSTIC: QUOTED vs COLLECTING Modes")
print("="*70 + "\n")

# Get channel
channel = WhatsAppChannel.objects.filter(
    v4_route__enabled=True, activo=True
).first()
if not channel:
    print("[ERROR] No active v4 channel")
    sys.exit(1)

phone_number_id = channel.phone_number_id
print(f"Channel: {phone_number_id}\n")

# Clean up old test data
with transaction.atomic():
    MensajeWhatsApp.objects.filter(
        conversacion__cliente__telefono__in=["51900111111", "51900222222"]
    ).delete()
    ConversacionWhatsApp.objects.filter(
        cliente__telefono__in=["51900111111", "51900222222"]
    ).delete()
    Cliente.objects.filter(telefono__in=["51900111111", "51900222222"]).delete()

# Setup service
chatwoot = RecordingChatwoot()
agent = ScriptedAgent([
    output(reply="Tu cotización actual es S/ 3500.00. ¿Deseas modificar algo?"),
    output(reply="Perfecto. Necesito saber: destino, piso y items."),
])
conversation_service = ConversationService(agent)
persistent_service = PersistentConversationService(
    conversation_service=conversation_service,
    repository=DjangoBotStateRepository(),
    crm_adapter=CRMV4Adapter(),
    chatwoot_adapter=chatwoot,
)
webhook_service = MetaWebhookV4Service(
    meta_adapter=FakeMetaAdapter(send_success=True),
    persistent_service=persistent_service,
    chatwoot_adapter=chatwoot,
)

# TEST 1: QUOTED MODE
print("="*70)
print("TEST 1: QUOTED MODE (status=quoted, price=3500, no LLM)")
print("="*70 + "\n")

cliente_q = Cliente.objects.create(telefono="51900111111")
lead_q = Lead.objects.create(cliente=cliente_q, whatsapp_channel=channel)
conv_q = ConversacionWhatsApp.objects.create(cliente=cliente_q, lead=lead_q, channel=channel)
bot_state_q = BotConversationState.objects.create(
    conversation_key=f"whatsapp:{conv_q.pk}",
    status="quoted",
    quote_price=3500.00,
    state_data={"origin_district": "San Isidro", "destination_district": "Miraflores"},
)

payload_q = meta_payload("cuantos cuesta", phone_number_id, "51900111111", "wamid.test.q1")
print("Sending: 'cuantos cuesta'")
print("Expected: Reply with price (no LLM)\n")
result_q = webhook_service.process_payload(payload_q)
print(f"Result: {result_q.status} (llm_calls={result_q.llm_calls})\n")

# TEST 2: COLLECTING MODE
print("="*70)
print("TEST 2: COLLECTING MODE (status=collecting, with LLM)")
print("="*70 + "\n")

cliente_c = Cliente.objects.create(telefono="51900222222")
lead_c = Lead.objects.create(cliente=cliente_c, whatsapp_channel=channel)
conv_c = ConversacionWhatsApp.objects.create(cliente=cliente_c, lead=lead_c, channel=channel)
bot_state_c = BotConversationState.objects.create(
    conversation_key=f"whatsapp:{conv_c.pk}",
    status="collecting",
    state_data={"origin_district": "San Isidro"},
)

payload_c = meta_payload("de Surco a Miraflores, piso 2 a 4", phone_number_id, "51900222222", "wamid.test.c1")
print("Sending: 'de Surco a Miraflores, piso 2 a 4'")
print("Expected: LLM extraction + reply (1 LLM call)\n")
result_c = webhook_service.process_payload(payload_c)
print(f"Result: {result_c.status} (llm_calls={result_c.llm_calls})\n")

print("="*70)
print("LOGS ABOVE show 'bot_v4_webhook_latency' with timing breakdown:")
print("  setup=X.Xms  context=X.Xms  process_turn=X.Xms  db=X.Xms  send=X.Xms  total=X.Xms")
print("="*70 + "\n")
