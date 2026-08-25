#!/usr/bin/env python
"""Test SSE directly to Django (bypass Nginx) to isolate the issue"""

import subprocess
import time
import requests
import json

print("=" * 80)
print("TEST: SSE Direct to Django (bypass Nginx)")
print("=" * 80)

# Setup session
session = requests.Session()

# Get CSRF token and login via Django directly
print("\n[1] Login directly to Django...")
response = session.get("http://localhost:8000/dashboard/login/")
csrf_token = response.cookies.get('csrftoken') or 'test'

login_data = {
    'username': 'testadmin',
    'password': 'testadmin123',
}
response = session.post(
    "http://localhost:8000/dashboard/api/auth/login/",
    json=login_data,
    headers={'X-CSRFToken': csrf_token}
)
print(f"[LOGIN] Status: {response.status_code}, Response: {response.text[:100]}")

# Get session cookie
session_id = session.cookies.get('sessionid')
print(f"[SESSION] {session_id}")

# Publish test event
print("\n[2] Publishing event...")
result = subprocess.run([
    "docker-compose", "exec", "-T", "django", "python", "manage.py", "shell"
], input="""
from apps.whatsapp.redis_events import get_event_bus
import time

bus = get_event_bus()
event = bus.publish("message.created", {
    "conversation_id": 2,
    "channel_id": 2,
    "cliente_id": 3,
    "message_id": 999,
    "meta_message_id": "TEST-DIRECT-DJANGO",
    "sender_type": "customer",
    "preview": "TEST-DIRECT-DJANGO",
    "timestamp": int(time.time() * 1000),
    "conversation": {
        "summary": "TEST-DIRECT-DJANGO",
        "last_activity": time.time(),
        "unread_delta": 1,
        "attention_state": "bot",
        "bot_paused": False
    }
})
print(f"Published: {event.id}")
""", capture_output=True, text=True
)
print(f"[PUBLISH] {result.stdout.strip()}")

# Connect to SSE directly
print("\n[3] Connecting to SSE (direct Django port 8000)...")
print("[SSE] Opening stream for 10 seconds...")

try:
    response = session.get(
        "http://localhost:8000/dashboard/whatsapp/api/events/stream/",
        timeout=15,
        stream=True
    )
    
    print(f"[SSE] Status: {response.status_code}")
    print(f"[SSE] Headers: {dict(response.headers)}")
    
    # Read stream
    lines = []
    start_time = time.time()
    for line in response.iter_lines(decode_unicode=True, chunk_size=1):
        elapsed = time.time() - start_time
        if elapsed > 10:
            print(f"[TIMEOUT] 10 seconds reached")
            break
        if line:
            lines.append(line)
            if "TEST-DIRECT-DJANGO" in line:
                print(f"[✓ FOUND] Event in stream at {elapsed:.2f}s:")
                print(f"   {line[:100]}")
    
    print(f"\n[STREAM] Total lines received: {len(lines)}")
    if lines:
        print("[FIRST 5 LINES]")
        for line in lines[:5]:
            print(f"  {line[:80]}")
    
    if "TEST-DIRECT-DJANGO" in "\n".join(lines):
        print("\n✓ SUCCESS: Event found in direct SSE stream!")
    else:
        print("\n✗ FAIL: Event NOT found in direct SSE stream")

except requests.exceptions.RequestException as e:
    print(f"[ERROR] {type(e).__name__}: {e}")
