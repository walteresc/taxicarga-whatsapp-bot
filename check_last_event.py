"""Check last event in Redis."""
import subprocess

cmd = [
    'docker', 'exec', 'taxicarga-api',
    'python', 'manage.py', 'shell', '-c',
    '''
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_e2e")
import django
django.setup()

from apps.whatsapp.redis_events import get_event_bus
import json

bus = get_event_bus()
r = bus.redis

# Get last event
last = r.xrevrange(bus.stream_key, count=1)
if last:
    evt_id, evt_data = last[0]
    print(f"Last event ID: {evt_id}")
    print(f"Raw data: {evt_data}")

    if b"data" in evt_data:
        data_json = evt_data[b"data"].decode()
        try:
            data = json.loads(data_json)
            print(f"Parsed: {data}")
            channel_id = data.get("channel_id")
            print(f"Channel ID: {channel_id}")
        except:
            print("Could not parse JSON data")
'''
]

result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
print(result.stdout)
if result.stderr:
    for line in result.stderr.split('\n'):
        if not line.startswith('['):
            print(line)
