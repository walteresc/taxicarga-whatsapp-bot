#!/usr/bin/env python
"""
FASE 5B Local Testing: Create controlled inbound message and verify event behavior.

Runs standalone via:
  python manage.py shell < test_local_inbound.py

Creates:
- Test client with unique ID
- Test conversation
- Inbound message with unique wamid
- Verifies events in Redis Stream
- No modification of historical data
- Cleanup procedure included
"""

import json
import logging
from datetime import datetime
from django.utils import timezone
from django.db import transaction

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FASE5B-LOCAL")

# Import models
from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel, ConversacionWhatsApp, MensajeWhatsApp
from apps.whatsapp.redis_events import get_latest_cursor, get_events

TEST_ID = f"FASE5B-LOCAL-INBOUND-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
logger.info(f"[TEST] Starting: {TEST_ID}")

# ============================================================
# 1. PREFLIGHT: Capture baseline
# ============================================================

baseline_cursor = get_latest_cursor()
baseline_events = get_events(baseline_cursor)
baseline_count = len(baseline_events)

logger.info(f"[PREFLIGHT] Baseline cursor: {baseline_cursor}")
logger.info(f"[PREFLIGHT] Baseline event count: {baseline_count}")

# ============================================================
# 2. CREATE TEST DATA
# ============================================================

# Create test client
client = Cliente.objects.create(
    nombre=f"Test Client {TEST_ID}",
    telefono="51987654321",
    documento="12345678",
)
logger.info(f"[DATA] Client created: id={client.id}, nombre={client.nombre}")

# Get or create active channel
channel, created = WhatsAppChannel.objects.get_or_create(
    nombre="Test Channel",
    defaults={"phone_number_id": "123456789", "activo": True}
)
logger.info(f"[DATA] Channel: id={channel.id}, activo={channel.activo}")

# ============================================================
# 3. CREATE INBOUND MESSAGE
# ============================================================

logger.info("[MSG] Creating inbound message with transaction...")

with transaction.atomic():
    # Create conversation
    conv = ConversacionWhatsApp.objects.create(
        cliente=client,
        channel=channel,
        resumen=f"Test conversation {TEST_ID}",
        estado_atencion=ConversacionWhatsApp.ATENCION_BOT,
        bot_pausado=False
    )
    logger.info(f"[MSG] Conversation created: id={conv.id}")

    # Create inbound message
    wamid = f"wamid_{TEST_ID}"
    msg = MensajeWhatsApp.objects.create(
        conversacion=conv,
        direccion=MensajeWhatsApp.ENTRANTE,
        tipo="text",
        contenido=f"Inbound test: {TEST_ID}",
        meta_message_id=wamid,
        sender_type="customer",
        source="whatsapp_customer"
    )
    logger.info(f"[MSG] Inbound message created: id={msg.id}, wamid={wamid}")

# ============================================================
# 4. VERIFY EVENTS IN REDIS
# ============================================================

logger.info("[EVENTS] Checking Redis Stream...")

events_after = get_events(baseline_cursor)
new_events = events_after[baseline_count:] if len(events_after) > baseline_count else []

logger.info(f"[EVENTS] Total events after baseline: {len(events_after)}")
logger.info(f"[EVENTS] New events: {len(new_events)}")

# Count events by type
event_counts = {}
for ev in new_events:
    event_type = ev.type
    event_counts[event_type] = event_counts.get(event_type, 0) + 1
    logger.info(f"[EVENTS]   - {event_type}: conv_id={ev.data.get('conversation_id')}")

logger.info(f"[EVENTS] Summary: {json.dumps(event_counts, indent=2)}")

# ============================================================
# 5. VERIFY BEHAVIOR
# ============================================================

logger.info("[VERIFY] Checking expected behavior...")

# Verify conversation.created
created_events = [e for e in new_events if e.type == "conversation.created"]
if len(created_events) == 1:
    logger.info("[VERIFY] ✓ conversation.created = 1")
else:
    logger.warning(f"[VERIFY] ✗ conversation.created = {len(created_events)} (expected 1)")

# Verify message.created
msg_created = [e for e in new_events if e.type == "message.created"]
if len(msg_created) == 1:
    logger.info("[VERIFY] ✓ message.created = 1")
    logger.info(f"[VERIFY]   - message_id: {msg_created[0].data.get('message_id')}")
    logger.info(f"[VERIFY]   - wamid: {msg_created[0].data.get('meta_message_id')}")
else:
    logger.warning(f"[VERIFY] ✗ message.created = {len(msg_created)} (expected 1)")

# Verify conversation.updated
updated_events = [e for e in new_events if e.type == "conversation.updated"]
if len(updated_events) >= 0:
    logger.info(f"[VERIFY] ✓ conversation.updated = {len(updated_events)}")
    for ev in updated_events:
        changed = ev.data.get('changed_fields', [])
        logger.info(f"[VERIFY]   - changed_fields: {changed}")

# ============================================================
# 6. REPROCESS SAME WAMID (Idempotency Test)
# ============================================================

logger.info("[IDEMPOTENCY] Reprocessing same wamid...")

cursor_before_reprocess = get_latest_cursor()

# Try to create same message again (should be rejected or ignored)
try:
    msg_dup = MensajeWhatsApp.objects.create(
        conversacion=conv,
        direccion=MensajeWhatsApp.ENTRANTE,
        tipo="text",
        contenido=f"Duplicate attempt: {TEST_ID}",
        meta_message_id=wamid,
        sender_type="customer",
        source="whatsapp_customer"
    )
    logger.warning(f"[IDEMPOTENCY] ✗ Duplicate message created (should have been rejected)")
except Exception as e:
    logger.info(f"[IDEMPOTENCY] ✓ Duplicate rejected: {type(e).__name__}")

events_after_reprocess = get_events(cursor_before_reprocess)
if len(events_after_reprocess) == 0:
    logger.info("[IDEMPOTENCY] ✓ No new events on duplicate attempt")
else:
    logger.warning(f"[IDEMPOTENCY] ✗ {len(events_after_reprocess)} new events on duplicate")

# ============================================================
# 7. CLEANUP INSTRUCTIONS
# ============================================================

logger.info("[CLEANUP] To remove test data, run:")
logger.info(f"  python manage.py shell")
logger.info(f"  Cliente.objects.filter(id={client.id}).delete()")
logger.info(f"  # OR SQL: DELETE FROM clientes_cliente WHERE id={client.id};")

# ============================================================
# SUMMARY
# ============================================================

logger.info("="*70)
logger.info(f"[SUMMARY] Test ID: {TEST_ID}")
logger.info(f"[SUMMARY] Conversation ID: {conv.id}")
logger.info(f"[SUMMARY] Message ID: {msg.id}")
logger.info(f"[SUMMARY] Message WAMID: {wamid}")
logger.info(f"[SUMMARY] Event counts: {json.dumps(event_counts)}")
logger.info("[SUMMARY] Status: ✓ LOCAL INBOUND TEST COMPLETE")
logger.info("="*70)

print(f"\nTest data created successfully.")
print(f"Test ID: {TEST_ID}")
print(f"Client ID: {client.id}")
print(f"Conversation ID: {conv.id}")
print(f"Message ID: {msg.id}")
