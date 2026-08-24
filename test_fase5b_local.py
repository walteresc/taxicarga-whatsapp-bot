#!/usr/bin/env python
"""FASE 5B Local Test: Inbound message with real event verification."""
import os
import sys
import django
import logging
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import transaction
from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp.redis_events import get_latest_cursor, get_events

logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
logger = logging.getLogger("FASE5B")

TEST_ID = f"F5B-{datetime.now().strftime('%H%M%S')}"
logger.info(f"Starting: {TEST_ID}")

# Get baseline
baseline_cursor = get_latest_cursor()
logger.info(f"Baseline cursor: {baseline_cursor}")

# Create test client with unique phone
phone = f"519{TEST_ID[-6:]}"
try:
    client = Cliente.objects.create(
        nombre=f"Test {TEST_ID}",
        telefono=phone,
        documento=TEST_ID
    )
    logger.info(f"✓ Client: id={client.id}")
except Exception as e:
    logger.warning(f"Client creation failed (may exist): {e}")
    client = Cliente.objects.filter(telefono=phone).first()
    if not client:
        raise

# Get first active channel
channel = WhatsAppChannel.objects.filter(activo=True).first()
if not channel:
    channel = WhatsAppChannel.objects.create(
        nombre=f"ch_{TEST_ID}",
        phone_number_id=TEST_ID,
        activo=True
    )
logger.info(f"✓ Channel: id={channel.id}, activo={channel.activo}")

# Create conversation + message within transaction
with transaction.atomic():
    conv = ConversacionWhatsApp.objects.create(
        cliente=client,
        channel=channel,
        resumen=f"Conv {TEST_ID}",
        estado_atencion='en_espera'
    )

    wamid = f"wamid_{TEST_ID}"
    msg = MensajeWhatsApp.objects.create(
        conversacion=conv,
        direccion=MensajeWhatsApp.ENTRANTE,
        tipo='text',
        contenido=f"Test {TEST_ID}",
        meta_message_id=wamid,
        sender_type='customer'
    )

logger.info(f"✓ Conversation: id={conv.id}")
logger.info(f"✓ Message: id={msg.id}, wamid={wamid}")

# Check events
events = get_events(baseline_cursor)
created = len([e for e in events if e.type == 'conversation.created'])
msg_created = len([e for e in events if e.type == 'message.created'])
updated = len([e for e in events if e.type == 'conversation.updated'])

logger.info(f"Events: created={created}, message.created={msg_created}, updated={updated}")
logger.info(f"✓ Status: {'PASS' if created == 1 and msg_created == 1 else 'INCOMPLETE'}")

print(f"\n{TEST_ID}|{client.id}|{conv.id}|{msg.id}|{wamid}")
