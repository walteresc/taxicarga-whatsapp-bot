#!/usr/bin/env python3
"""
Test SSE auth: verify session is preserved in request.
Simulates browser: login, then try SSE without force_login.
"""
import os
import sys
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_e2e')

import django
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from apps.whatsapp.redis_events import publish_event
from apps.dashboard.views_sse import sse_events_stream
from django.test import RequestFactory
from django.utils import timezone

client = Client()

# Login via form (like browser does)
print("\n=== SSE AUTH TEST ===")
print("[1] Logging in via form...")

user, _ = User.objects.get_or_create(username='e2e_test')
user.set_password('e2e_test_pass_123')
user.save()

login_resp = client.post('/dashboard/login/', {
    'username': 'e2e_test',
    'password': 'e2e_test_pass_123',
})
print(f"[OK] Login response: {login_resp.status_code}")

# Get session cookie
session_key = client.cookies.get('sessionid')
if not session_key:
    print("[FAIL] No session cookie after login")
    sys.exit(1)
print(f"[OK] Session key: {session_key.value[:20]}...")

# Now try SSE as logged-in browser would
print("\n[2] Opening SSE as authenticated user...")
sse_resp = client.get('/dashboard/whatsapp/api/events/stream/')
print(f"[SSE] Status: {sse_resp.status_code}")

if sse_resp.status_code == 302:
    print(f"[FAIL] Got redirect (not authenticated): {sse_resp.url}")
    sys.exit(1)
elif sse_resp.status_code == 403:
    print(f"[FAIL] Got forbidden (no permission)")
    sys.exit(1)
elif sse_resp.status_code == 200:
    print(f"[OK] Got 200 OK, SSE stream opened")
else:
    print(f"[FAIL] Unexpected status: {sse_resp.status_code}")
    sys.exit(1)

# Read first few chunks
print("\n[3] Reading chunks...")
chunk_count = 0
for chunk in sse_resp.streaming_content:
    chunk_count += 1
    chunk_str = chunk.decode('utf-8') if isinstance(chunk, bytes) else chunk

    if 'event:' in chunk_str or 'id:' in chunk_str:
        print(f"\n[CHUNK {chunk_count}]")
        print(repr(chunk_str[:150]))

    if chunk_count >= 5:
        break

print(f"\n[OK] Read {chunk_count} chunks successfully")
print("[DONE] SSE auth test PASS - session preserved")
