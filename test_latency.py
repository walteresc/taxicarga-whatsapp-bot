#!/usr/bin/env python
"""
Test latency: QUOTED vs COLLECTING modes
"""
import os
import django
import json
import time
from unittest.mock import Mock

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp, MensajeWhatsApp
from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.whatsapp_bot_v4.models import BotConversationState
from apps.whatsapp_bot_v4.services.meta_webhook_service import MetaWebhookV4Service
from apps.whatsapp_bot_v4.services.persistent_conversation_service import PersistentConversationService
from apps.whatsapp_bot_v4.services.conversation_service import ConversationService
from apps.whatsapp_bot_v4.ai.agent import ConversationAgent
from apps.whatsapp_bot_v4.adapters.meta import MetaV4Adapter, MetaSendResult
from apps.whatsapp_bot_v4.adapters.crm import CRMV4Adapter
from apps.whatsapp_bot_v4.repositories.state import DjangoBotStateRepository
from apps.whatsapp_bot_v4.tests.meta_fakes import FakeMetaAdapter, RecordingChatwoot
from apps.whatsapp_bot_v4.tests.fakes import ScriptedAgent, output


def meta_payload(text, phone_number_id, customer):
    """Build Meta webhook payload"""
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": phone_number_id},
            "messages": [{
                "from": customer,
                "id": f"wamid.{time.time()}",
                "timestamp": str(int(time.time())),
                "type": "text",
                "text": {"body": text},
            }],
        }}]}],
    }


def setup_quoted_conversation(phone_number_id, customer_id):
    """Setup a QUOTED conversation with price"""
    channel = WhatsAppChannel.objects.filter(phone_number_id=phone_number_id).first()
    cliente, _ = Cliente.objects.get_or_create(telefono=customer_id)
    lead = Lead.objects.create(cliente=cliente, whatsapp_channel=channel)
    conversation = ConversacionWhatsApp.objects.create(cliente=cliente, lead=lead, channel=channel)

    # Create bot state in QUOTED status with price
    bot_state, _ = BotConversationState.objects.get_or_create(
        conversation_key=f"whatsapp:{conversation.pk}",
        defaults={
            "status": "quoted",
            "quote_price": 3500.00,
            "state_data": {
                "origin_district": "San Isidro",
                "destination_district": "Miraflores",
                "origin_floor": 2,
                "destination_floor": 4,
                "items": ["cama", "espejo"],
            },
        }
    )
    return conversation, bot_state


def setup_collecting_conversation(phone_number_id, customer_id):
    """Setup a COLLECTING conversation (no price yet)"""
    channel = WhatsAppChannel.objects.filter(phone_number_id=phone_number_id).first()
    cliente, _ = Cliente.objects.get_or_create(telefono=customer_id)
    lead = Lead.objects.create(cliente=cliente, whatsapp_channel=channel)
    conversation = ConversacionWhatsApp.objects.create(cliente=cliente, lead=lead, channel=channel)

    # Create bot state in COLLECTING status
    bot_state, _ = BotConversationState.objects.get_or_create(
        conversation_key=f"whatsapp:{conversation.pk}",
        defaults={
            "status": "collecting",
            "state_data": {
                "origin_district": "San Isidro",
            },
        }
    )
    return conversation, bot_state


print("=" * 60)
print("LATENCY DIAGNOSTIC TEST")
print("=" * 60)

# Get channel
channel = WhatsAppChannel.objects.filter(
    v4_route__enabled=True, activo=True
).first()
if not channel:
    print("[FAIL] No active v4 channel found")
    exit(1)

phone_number_id = channel.phone_number_id
print(f"\nUsing channel: {phone_number_id}")

# Setup conversations
print("\n1. Setting up QUOTED conversation...")
quoted_conv, quoted_state = setup_quoted_conversation(phone_number_id, "51911112222")
print(f"   Conversation ID: {quoted_conv.pk}")
print(f"   Status: {quoted_state.status}, Price: {quoted_state.quote_price}")

print("\n2. Setting up COLLECTING conversation...")
collecting_conv, collecting_state = setup_collecting_conversation(phone_number_id, "51922223333")
print(f"   Conversation ID: {collecting_conv.pk}")
print(f"   Status: {collecting_state.status}")

# Setup service
fake_adapter = FakeMetaAdapter(send_success=True)
chatwoot = RecordingChatwoot()

# Use ScriptedAgent for latency testing (no LLM calls, fast)
agent = ScriptedAgent([
    output(reply="Tu cotización actual es S/ 3500.00. ¿Deseas modificar algo?"),
    output(reply="Perfecto. Necesito saber los detalles del destino..."),
])

conversation_service = ConversationService(agent)
persistent_service = PersistentConversationService(
    conversation_service=conversation_service,
    repository=DjangoBotStateRepository(),
    crm_adapter=CRMV4Adapter(),
    chatwoot_adapter=chatwoot,
)
webhook_service = MetaWebhookV4Service(
    meta_adapter=fake_adapter,
    persistent_service=persistent_service,
    chatwoot_adapter=chatwoot,
)

print("\n" + "=" * 60)
print("TEST 1: QUOTED MODE (no LLM)")
print("=" * 60)

# Clear previous messages to avoid UNIQUE constraint
from apps.whatsapp.models import MensajeWhatsApp
MensajeWhatsApp.objects.filter(conversacion__cliente__telefono="51911112222").delete()

payload_quoted = meta_payload(
    text="cuánto cuesta",
    phone_number_id=phone_number_id,
    customer="51911112222",
)

try:
    result = webhook_service.process_payload(payload_quoted)
    print(f"[OK] Status: {result.status}")
    print(f"   Reply sent: {result.outbound_message_id}")
    print(f"   LLM calls: {result.llm_calls}")
except Exception as e:
    print(f"[ERROR] {e}")

print("\n" + "=" * 60)
print("TEST 2: COLLECTING MODE (with LLM)")
print("=" * 60)

payload_collecting = meta_payload(
    text="de San Isidro a Miraflores, del piso 2 al 4 con escaleras",
    phone_number_id=phone_number_id,
    customer="51922223333",
)

try:
    result = webhook_service.process_payload(payload_collecting)
    print(f"[OK] Status: {result.status}")
    print(f"   Reply sent: {result.outbound_message_id}")
    print(f"   LLM calls: {result.llm_calls}")
except Exception as e:
    print(f"[ERROR] {e}")

print("\n" + "=" * 60)
print("Latency Summary")
print("=" * 60)

# Query logs from database
from django.db import connection
from django.test.utils import CaptureQueriesContext

print("""
The timings are logged via Django logger as:
  bot_v4_webhook_latency

Format: setup=X.Xms context=X.Xms process_turn=X.Xms db=X.Xms send=X.Xms total=X.Xms

These logs show:
- setup: Identity resolution + message persistence
- context: Loading conversation history
- process_turn: LLM call (COLLECTING) or direct reply (QUOTED)
- db: Creating outgoing message record
- send: HTTP to Meta WhatsApp API
- total: End-to-end latency
""")
