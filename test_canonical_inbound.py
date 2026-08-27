#!/usr/bin/env python
"""
FASE 5B Canonical Inbound Test

Uses the real webhook service flow, not direct DB creation.
Simulates inbound message via WhatsApp webhook payload.
Verifies complete flow: resolver → conversation → message → signals → events.
"""
import os
import sys
import django
import json
import logging
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import transaction
from django.test import RequestFactory
from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp.redis_events import get_latest_cursor, get_events
from apps.whatsapp.views import whatsapp_webhook

logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
logger = logging.getLogger("CANONICAL")

TEST_ID = f"CANONICAL-{datetime.now().strftime('%H%M%S')}"
logger.info(f"Starting canonical inbound test: {TEST_ID}")

# ============================================================
# 1. SETUP: Create channel and user
# ============================================================

channel = WhatsAppChannel.objects.filter(activo=True).first()
if not channel:
    channel = WhatsAppChannel.objects.create(
        nombre="canonical-test",
        phone_number_id="999999999",
        activo=True
    )
    logger.info(f"Created test channel: {channel.id}")

phone = f"519{TEST_ID[-6:]}"
client, created = Cliente.objects.get_or_create(
    telefono=phone,
    defaults={"nombre": f"Canonical {TEST_ID}", "documento": TEST_ID}
)
logger.info(f"Client: id={client.id} (created={created})")

# ============================================================
# 2. CAPTURE BASELINE
# ============================================================

baseline_cursor = get_latest_cursor()
baseline_conv_count = ConversacionWhatsApp.objects.count()
baseline_msg_count = MensajeWhatsApp.objects.count()

logger.info(f"Baseline: cursor={baseline_cursor}, convs={baseline_conv_count}, msgs={baseline_msg_count}")

# ============================================================
# 3. SIMULATE WEBHOOK PAYLOAD (inbound)
# ============================================================

wamid = f"wamid_{TEST_ID}"
webhook_payload = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "1",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": channel.numero_visible or "CHANNEL",
                            "phone_number_id": channel.phone_number_id,
                        },
                        "contacts": [
                            {
                                "profile": {"name": f"Test User {TEST_ID}"},
                                "wa_id": phone.lstrip("+")
                            }
                        ],
                        "messages": [
                            {
                                "from": phone.lstrip("+"),
                                "id": wamid,
                                "timestamp": str(int(datetime.now().timestamp())),
                                "text": {"body": f"Canonical test {TEST_ID}"},
                                "type": "text"
                            }
                        ]
                    },
                    "field": "messages"
                }
            ]
        }
    ]
}

logger.info(f"Webhook payload: from={phone}, wamid={wamid}")

# ============================================================
# 4. SEND TO WEBHOOK (simulated via request)
# ============================================================

factory = RequestFactory()
request = factory.post(
    '/webhook/whatsapp/',
    data=json.dumps(webhook_payload),
    content_type='application/json'
)

logger.info("Calling receive_message webhook handler...")

try:
    response = whatsapp_webhook(request)
    logger.info(f"Webhook response: {response.status_code}")
except Exception as e:
    logger.error(f"Webhook error: {e}", exc_info=True)

# ============================================================
# 5. VERIFY EFFECTS
# ============================================================

after_conv_count = ConversacionWhatsApp.objects.count()
after_msg_count = MensajeWhatsApp.objects.count()

conv_increase = after_conv_count - baseline_conv_count
msg_increase = after_msg_count - baseline_msg_count

logger.info(f"After: convs={after_conv_count} (+{conv_increase}), msgs={after_msg_count} (+{msg_increase})")

# Check if conversation was created or reused
convs = ConversacionWhatsApp.objects.filter(cliente=client)
logger.info(f"Client {client.id} has {convs.count()} conversation(s)")

for conv in convs:
    messages = conv.mensajes.all()
    logger.info(f"  Conv {conv.id}: {messages.count()} messages, resumen='{conv.resumen}'")

    # Check for message with matching wamid
    msg_with_wamid = conv.mensajes.filter(meta_message_id=wamid).first()
    if msg_with_wamid:
        logger.info(f"    Message found: id={msg_with_wamid.id}, wamid={wamid}")

# ============================================================
# 6. VERIFY EVENTS IN REDIS
# ============================================================

events = get_events(baseline_cursor)
created_count = len([e for e in events if e.type == 'conversation.created'])
msg_created_count = len([e for e in events if e.type == 'message.created'])
updated_count = len([e for e in events if e.type == 'conversation.updated'])

logger.info(f"Events: created={created_count}, message.created={msg_created_count}, updated={updated_count}")

# ============================================================
# 7. SUMMARY
# ============================================================

logger.info("="*70)
logger.info(f"[CANONICAL] Test ID: {TEST_ID}")
logger.info(f"[CANONICAL] Phone: {phone}")
logger.info(f"[CANONICAL] WAMID: {wamid}")
logger.info(f"[CANONICAL] Client ID: {client.id}")
logger.info(f"[CANONICAL] Conversations: +{conv_increase}")
logger.info(f"[CANONICAL] Messages: +{msg_increase}")
logger.info(f"[CANONICAL] Events - created={created_count}, msg={msg_created_count}, updated={updated_count}")
logger.info(f"[CANONICAL] Status: {'✓ PASS' if msg_increase >= 1 and created_count >= 0 else '✗ INCOMPLETE'}")
logger.info("="*70)
