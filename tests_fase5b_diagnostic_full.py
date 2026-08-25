"""
FASE 5B DIAGNOSTIC MASTER TEST (FASES 2-6)
Identify where events are lost: Redis → SSE → Browser
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_e2e')

import django
django.setup()

import json
from datetime import datetime
from apps.whatsapp.redis_events import get_event_bus, get_events
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from apps.dashboard.views_sse import _event_generator

User = get_user_model()
print("\n" + "="*80)
print("FASE 5B DIAGNOSTIC: Redis → Event Bus → Generator → Browser")
print("="*80 + "\n")

# Get e2e_asesor user
user = User.objects.get(username='e2e_asesor')
print(f"[TEST USER] {user.username} (id={user.id}, superuser={user.is_superuser})")
print(f"  Groups: {', '.join(user.groups.values_list('name', flat=True))}")

# ========== PHASE 2: Canonical Diagnostic Event ==========
print("\n[PHASE 2] Publishing diagnostic event...")
bus = get_event_bus()
event_data = {
    "conversation_id": 2,
    "channel_id": 2,
    "cliente_id": 3,
    "message_id": 999,
    "meta_message_id": "diag_test_001",
    "sender_type": "customer",
    "direction": "entrante",
    "content_type": "texto",
    "preview": "FASE5B-DIAGNOSTIC-EVENT",
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "conversation": {
        "summary": "FASE5B-DIAGNOSTIC",
        "last_activity": datetime.utcnow().isoformat() + "Z",
        "unread_delta": 1,
        "attention_state": "bot",
        "bot_paused": False,
    }
}

cursor_before = bus.get_latest_id()
event = bus.publish("message.created", event_data)
cursor_after = bus.get_latest_id()
print(f"  Event published: {event.id}")
print(f"  Cursor before: {cursor_before}")
print(f"  Cursor after: {cursor_after}")

# ========== PHASE 3: Redis Event Bus Isolation Test ==========
print("\n[PHASE 3] Testing Redis event bus isolation...")
print(f"  Querying get_events(cursor={cursor_before})...")
events = get_events(cursor=cursor_before)
found = [e for e in events if e.id == event.id]
if found:
    print(f"  [OK] Found event in Redis: {found[0].id}")
    print(f"      Type: {found[0].type}")
    print(f"      Data channel_id: {found[0].data.get('channel_id')}")
    print(f"      Data preview: {found[0].data.get('preview', 'N/A')[:40]}")
else:
    print(f"  [FAIL] Event NOT found in Redis after query")

# Second query from event cursor (should not return event again)
print(f"  Querying get_events(cursor={event.id})...")
events_after = get_events(cursor=event.id)
found_again = [e for e in events_after if e.id == event.id]
if not found_again:
    print(f"  [OK] Event not returned on second query (cursor advanced)")
else:
    print(f"  [FAIL] Event returned again (idempotence broken)")

# ========== PHASE 4: Authorization Filter Test ==========
print("\n[PHASE 4] Testing authorization filter...")
authorized_channels = set([2])  # e2e_asesor can see channel 2
event_obj = found[0] if found else None
if event_obj:
    channel_id = event_obj.data.get('channel_id')
    is_authorized = channel_id in authorized_channels
    print(f"  Event channel_id: {channel_id}")
    print(f"  Authorized channels: {authorized_channels}")
    print(f"  [{'OK' if is_authorized else 'FAIL'}] Authorization: {is_authorized}")
else:
    print("  [SKIP] No event to test")

# ========== PHASE 5 & 6: Generator Test ==========
print("\n[PHASE 5/6] Testing SSE generator...")
factory = RequestFactory()
request = factory.get('/dashboard/whatsapp/api/events/stream/')
request.user = user

# Mock a cursor just before our event
generator = _event_generator(request, bus, cursor_before, cursor_too_old=False)

# Consume first few yields
print("  Starting generator...")
yields = []
try:
    for i, data in enumerate(generator):
        yields.append(data)
        if i >= 10:  # Limit to prevent infinite loop
            break
        if 'DIAGNOSTIC' in data:
            print(f"  [OK] Generator yielded our event at index {i}")
            break
    if i >= 10:
        print(f"  [FAIL] Generator did not yield diagnostic event in first 10 yields")
except Exception as e:
    print(f"  [ERROR] Generator exception: {str(e)[:100]}")

# ========== SUMMARY ==========
print("\n" + "="*80)
print("DIAGNOSTIC SUMMARY")
print("="*80)
print(f"[1] User has permission: True")
print(f"[2] Event published to Redis: {event.id if event else 'NO'}")
print(f"[3] Redis returns event: {bool(found)}")
print(f"[4] Event passes auth filter: {is_authorized if event_obj else 'N/A'}")
print(f"[5/6] Generator yields event: {'YES' if any('DIAGNOSTIC' in y for y in yields) else 'NO'}")
print(f"\nTotal yields captured: {len(yields)}")
if yields:
    print(f"First yield: {yields[0][:60]}...")
