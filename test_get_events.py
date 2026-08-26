"""Test get_events with real cursor."""
import subprocess

cmd = [
    'docker', 'exec', 'taxicarga-api',
    'python', 'manage.py', 'shell', '-c',
    '''
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_e2e")
import django
django.setup()

from apps.whatsapp.redis_events import get_event_bus, get_events

# Test with actual cursor from frontend
cursor = "1787703460351-0"

print(f"Testing get_events(cursor={cursor})")
print("-" * 80)

events = get_events(cursor=cursor)
print(f"Result: {len(events)} events")

for evt in events:
    print(f"  Event: {evt.id} ({evt.type})")
    print(f"    Channel ID: {evt.data.get('channel_id')}")
    print(f"    Preview: {evt.data.get('preview')}")
'''
]

result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
print(result.stdout)
