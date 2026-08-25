#!/usr/bin/env python
import os
import sys
import django
import time

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_e2e')
django.setup()

from apps.whatsapp.redis_events import get_event_bus, get_latest_cursor, publish_event

print("=" * 80)
print("TEST: Event Generator Direct")
print("=" * 80)

bus = get_event_bus()
print(f"Bus: {type(bus).__name__}")

# Get initial cursor
cursor_before = get_latest_cursor()
print(f"\n[1] Cursor before: {cursor_before}")

# Publish a test event
test_event = {
    'type': 'message.created',
    'conversation_id': 999,
    'data': {'test': True, 'timestamp': time.time()}
}
event_id = publish_event(test_event, channel_id=2)
print(f"[2] Published event: {event_id}")

# Get new cursor
cursor_after = get_latest_cursor()
print(f"[3] Cursor after: {cursor_after}")

# Try to get events
events = bus.get_events_since(cursor_before)
print(f"[4] Events since {cursor_before}: {len(events)}")
if events:
    for ev in events:
        print(f"    - {ev}")
