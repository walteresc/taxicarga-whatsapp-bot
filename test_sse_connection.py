"""Test if SSE connection actually reaches the generator."""
import subprocess
import time
import requests


# Step 1: Login
print("[1] Login")
session = requests.Session()
resp = session.post(
    'http://localhost:8001/dashboard/api/auth/login/',
    json={'username': 'e2e_test', 'password': 'e2e_test_password'}
)
sessionid = session.cookies.get_dict().get('sessionid')
print(f"[OK] sessionid={sessionid[:20]}")

# Step 2: Start log capture in background
print("\n[2] Start log capture")
log_process = subprocess.Popen(
    ['docker', 'logs', '-f', 'taxicarga-api'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

time.sleep(0.5)

# Step 3: Open SSE connection (non-blocking, using curl in background)
print("\n[3] Open SSE connection")
sse_process = subprocess.Popen(
    ['curl', '-i',
     'http://localhost:8001/dashboard/whatsapp/api/events/stream/',
     '-b', f'sessionid={sessionid}',
     '--max-time', '5'],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

time.sleep(1)

# Step 4: Publish event
print("[4] Publish event")
pub_cmd = [
    'docker', 'exec', 'taxicarga-api',
    'python', '-c',
    '''
import os, time
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_e2e"
import django
django.setup()

print("DEBUG: About to publish", flush=True)

from apps.whatsapp.redis_events import get_event_bus
bus = get_event_bus()
event = bus.publish("message.created", {
    "conversation_id": 2,
    "channel_id": 2,
    "correlation_id": "conn-test-" + str(int(time.time()*1000))
})
print(f"DEBUG: Published {event.id}", flush=True)
'''
]

result = subprocess.run(pub_cmd, capture_output=True, text=True, timeout=10)
print(result.stdout[:200])

# Step 5: Wait and capture logs
print("\n[5] Waiting 5 seconds, capturing logs...")
time.sleep(5)

# Step 6: Read captured logs
print("\n[6] Reading captured logs...")

# Terminate the log process
log_process.terminate()

# Read output
try:
    stdout, _ = log_process.communicate(timeout=2)
except:
    log_process.kill()
    stdout = ""

print("\n[LOGS - SSE related]")
for line in stdout.split('\n'):
    if 'SSE' in line or 'GEN' in line or 'conn-test' in line:
        print(f"  {line[:120]}")

if not any('SSE' in line for line in stdout.split('\n')):
    print("  [NO SSE LOGS FOUND]")

# Step 7: Check curl result
print("\n[7] SSE response status")
try:
    curl_stdout, curl_stderr = sse_process.communicate(timeout=2)
except:
    sse_process.kill()
    curl_stdout, curl_stderr = "", ""

first_line = curl_stdout.split('\n')[0] if curl_stdout else "No response"
print(f"  {first_line}")

if 'text/event-stream' in curl_stdout:
    print("  [OK] Got text/event-stream header")
    # Check for connected message
    if 'connected' in curl_stdout:
        print("  [OK] Got 'connected' message")
    else:
        print("  [MISSING] No 'connected' message")
else:
    print("  [MISSING] No text/event-stream header")

print("\n[DONE]")
