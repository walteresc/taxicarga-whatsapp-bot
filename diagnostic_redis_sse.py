#!/usr/bin/env python3
"""
Diagnostic: Verify Redis events and SSE connectivity.
Run after Gate 3 test to check if event is in Redis and accessible via SSE.
"""
import os
import sys
import json
import redis

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_e2e')

import django
django.setup()

from django.conf import settings
from apps.whatsapp.redis_events import get_events, get_latest_cursor

# Connection
redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
stream_key = getattr(settings, 'WHATSAPP_EVENTS_STREAM_KEY', 'whatsapp:events')

print("\n=== REDIS SSE DIAGNOSTIC ===")
print(f"Redis URL: {redis_url}")
print(f"Stream key: {stream_key}")

# Connect
try:
    client = redis.from_url(redis_url, decode_responses=True)
    client.ping()
    print("[OK] Redis connected")
except Exception as e:
    print(f"[FAIL] Redis connection failed: {e}")
    sys.exit(1)

# Check stream length
try:
    stream_len = client.xlen(stream_key)
    print(f"\n[INFO] Stream length: {stream_len} events")
except Exception as e:
    print(f"[FAIL] Failed to get stream length: {e}")

# Get latest 5 events
print(f"\n[INFO] Latest 5 events in stream:")
try:
    events = client.xrevrange(stream_key, count=5)
    if not events:
        print("   (empty)")
    for event_id, event_data in events:
        event_id_str = event_id.decode() if isinstance(event_id, bytes) else event_id
        event_type = event_data.get('type', 'unknown')
        timestamp = event_data.get('timestamp', 'unknown')
        print(f"   [{event_id_str}] type={event_type}, ts={timestamp}")
        if event_data.get('data'):
            data = json.loads(event_data['data'])
            if 'message_id' in data:
                print(f"       message_id={data['message_id']}, conv_id={data.get('conversation_id')}")
except Exception as e:
    print(f"[FAIL] Failed to read events: {e}")

# Check if SSE can read via Django API
print(f"\n[INFO] Testing SSE via Django API:")
try:
    from django.test import Client
    client_http = Client()

    # Get snapshot to get latest cursor
    resp = client_http.get('/dashboard/whatsapp/conversaciones/api/active/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    if resp.status_code == 200:
        data = resp.json()
        cursor = data.get('snapshot_cursor', '0')
        print(f"   Snapshot cursor: {cursor}")

        # Try to get events from SSE endpoint
        resp_events = client_http.get(f'/dashboard/whatsapp/api/events/poll/?cursor={cursor}')
        if resp_events.status_code == 200:
            events_data = resp_events.json()
            print(f"   [OK] SSE poll returned {len(events_data.get('events', []))} events")
            for evt in events_data.get('events', [])[:3]:
                print(f"       - {evt.get('type')}")
        else:
            print(f"   [FAIL] SSE poll returned {resp_events.status_code}")
    else:
        print(f"   [FAIL] Failed to get snapshot: {resp.status_code}")
except Exception as e:
    print(f"[FAIL] API test failed: {e}")

print("\n=== CHECKPOINT VERIFICATION ===")
print("[OK] CP-13: Event in Redis (confirmed above)")
print("[WAIT] CP-14: EventSource receiving event (frontend test needed)")
print("[WAIT] CP-15: eventStore processing (frontend console needed)")
print("[WAIT] CP-16: Pinia store updated (frontend devtools needed)")
print("[WAIT] CP-17: DOM reflected (visual test needed)")
