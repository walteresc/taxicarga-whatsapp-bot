#!/usr/bin/env python3
"""
Direct SSE stream test - capture raw chunks from generator.
Authenticates, publishes event, reads SSE frames.
"""
import os
import sys
import json
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_e2e')

import django
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from django.utils import timezone
from apps.whatsapp.redis_events import publish_event, get_event_bus

# Auth
client = Client()
user, _ = User.objects.get_or_create(username='e2e_test')
client.force_login(user)

print("\n=== SSE DIRECT TEST ===")
print("[1] Publishing test event...")

# Publish event
event_data = {
    'conversation_id': 999,
    'channel_id': 1,
    'cliente_id': 1,
    'message_id': 9999,
    'meta_message_id': 'test-wamid-direct',
    'sender_type': 'customer',
    'direction': 'entrante',
    'content_type': 'text',
    'preview': 'Direct SSE test message',
    'timestamp': timezone.now().isoformat(),
    'conversation': {
        'summary': 'Test',
        'last_activity': timezone.now().isoformat(),
        'unread_count': 1,
        'attention_state': 'bot',
        'bot_paused': False,
    }
}

evt = publish_event('message.created', event_data)
if evt:
    print(f"[OK] Event published: ID={evt.id}")
else:
    print("[FAIL] Event publishing failed")
    sys.exit(1)

print("\n[2] Opening SSE stream...")

# Open SSE as streaming response (Django test client)
# Note: Can't use client.get() for streaming, need to test via HTTP
# Instead, use Django's response object directly

from apps.dashboard.views_sse import sse_events_stream
from django.test import RequestFactory

factory = RequestFactory()
request = factory.get('/dashboard/whatsapp/api/events/stream/')
request.user = user

print(f"[3] Calling SSE view...")
response = sse_events_stream(request)

print(f"[OK] Response status: {response.status_code}")
print(f"[OK] Content-Type: {response.get('Content-Type', 'not set')}")

# Read chunks
print("\n[4] Reading SSE chunks...")
chunk_count = 0
timeout = time.time() + 10

try:
    for chunk in response.streaming_content:
        chunk_count += 1
        chunk_str = chunk.decode('utf-8') if isinstance(chunk, bytes) else chunk

        print(f"\n--- Chunk {chunk_count} ---")
        print(repr(chunk_str[:200]))  # First 200 chars

        # Look for our event
        if 'message.created' in chunk_str:
            print("[FOUND] message.created event!")
            print(f"Full chunk:\n{chunk_str}")

            # Parse SSE format
            lines = chunk_str.strip().split('\n')
            event_type = None
            event_id = None
            event_data = None

            for line in lines:
                if line.startswith('event:'):
                    event_type = line[6:].strip()
                elif line.startswith('id:'):
                    event_id = line[3:].strip()
                elif line.startswith('data:'):
                    event_data = line[5:].strip()

            print(f"\n[PARSE] event_type={event_type}")
            print(f"[PARSE] event_id={event_id}")
            print(f"[PARSE] event_data={event_data[:100] if event_data else 'None'}...")

            if event_data:
                try:
                    data_obj = json.loads(event_data)
                    print(f"[PARSE] conversation_id={data_obj.get('conversation_id')}")
                    print(f"[PARSE] message_id={data_obj.get('message_id')}")
                except:
                    print("[PARSE] Failed to parse event data JSON")
            break

        if time.time() > timeout:
            print("[TIMEOUT] No message.created received in 10 seconds")
            break

except Exception as e:
    print(f"[ERROR] Reading chunks failed: {e}")
    import traceback
    traceback.print_exc()

print(f"\n[SUMMARY] Read {chunk_count} chunks total")
print("[DONE]")
