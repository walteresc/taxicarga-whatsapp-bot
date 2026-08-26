"""Test if events are delivered through SSE (curl streaming)."""
import subprocess
import time
import requests
import threading


def run_curl_sse(sessionid, output_file):
    """Run curl to capture SSE stream."""
    cmd = [
        'curl', '-s', '-N',  # -N: no buffer
        'http://localhost:8001/dashboard/whatsapp/api/events/stream/',
        '-b', f'sessionid={sessionid}',
        '--max-time', '10'
    ]

    with open(output_file, 'w') as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL, text=True)


# Step 1: Login
print("[1] Login")
session = requests.Session()
resp = session.post(
    'http://localhost:8001/dashboard/api/auth/login/',
    json={'username': 'e2e_test', 'password': 'e2e_test_password'}
)
sessionid = session.cookies.get_dict().get('sessionid')
print(f"[OK] sessionid={sessionid[:20]}")

# Step 2: Start curl in background thread
print("\n[2] Start SSE stream capture")
output_file = '/tmp/sse_stream.txt'
curl_thread = threading.Thread(
    target=run_curl_sse,
    args=(sessionid, output_file),
    daemon=True
)
curl_thread.start()
time.sleep(2)  # Give curl time to connect

# Step 3: Publish event
print("[3] Publish event")
correlation = f"curl-test-{int(time.time()*1000)}"
pub_cmd = [
    'docker', 'exec', 'taxicarga-api',
    'python', '-c',
    f'''
import os, time
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_e2e"
import django
django.setup()

from apps.whatsapp.redis_events import get_event_bus
bus = get_event_bus()
event = bus.publish("message.created", {{
    "conversation_id": 2,
    "channel_id": 2,
    "correlation_id": "{correlation}"
}})
print(f"PUBLISHED:{{event.id}}")
'''
]

result = subprocess.run(pub_cmd, capture_output=True, text=True, timeout=10)
for line in result.stdout.split('\n'):
    if 'PUBLISHED' in line:
        print(f"[OK] {line}")

# Step 4: Wait for delivery
print("\n[4] Waiting 5 seconds for delivery...")
time.sleep(5)

# Step 5: Read stream capture
print("\n[5] Analyzing SSE stream...")

try:
    with open(output_file, 'r') as f:
        content = f.read()
except:
    content = "[Could not read file]"

print(f"Stream content ({len(content)} bytes):")
print("-" * 80)
print(content[:1000])
print("-" * 80)

# Check for key markers
if ': connected' in content:
    print("[OK] Got 'connected' marker")
else:
    print("[FAIL] No 'connected' marker")

if correlation in content:
    print(f"[OK] Got correlation_id: {correlation}")
else:
    print(f"[FAIL] No correlation_id: {correlation}")

if 'message.created' in content:
    print("[OK] Got 'message.created' event")
else:
    print("[FAIL] No event delivered")

if 'heartbeat' in content:
    print("[OK] Got heartbeat")

print("\n[DONE]")
