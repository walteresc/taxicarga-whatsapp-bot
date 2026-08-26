"""Debug v2: Con cache buster."""
import asyncio
import subprocess
import uuid
import time
import requests
from playwright.async_api import async_playwright


async def http_login():
    session = requests.Session()
    resp = session.post(
        'http://localhost:8001/dashboard/api/auth/login/',
        json={'username': 'e2e_test', 'password': 'e2e_test_password'}
    )
    return session.cookies.get_dict().get('sessionid') if resp.status_code == 200 else None


async def publish_event(correlation_id: str) -> str:
    cmd = [
        'docker', 'exec', 'taxicarga-api',
        'python', 'manage.py', 'shell', '-c',
        f'''
import os, time
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_e2e"
import django
django.setup()

from apps.whatsapp.models import MensajeWhatsApp
from apps.whatsapp.redis_events import get_event_bus

msg = MensajeWhatsApp.objects.get(id=117)

event_data = {{
    "type": "message.created",
    "conversation_id": msg.conversacion_id,
    "message_id": msg.id,
    "channel_id": msg.conversacion.channel_id,
    "cliente_id": msg.conversacion.cliente_id,
    "content": "DEBUG2",
    "sender_type": msg.sender_type,
    "direccion": msg.direccion,
    "source": msg.origen,
    "timestamp": msg.fecha_mensaje.isoformat(),
    "unread_delta": 1,
    "correlation_id": "{correlation_id}",
    "data": {{
        "conversation_id": msg.conversacion_id,
        "message_id": msg.id,
        "sender_type": msg.sender_type,
        "preview": "DEBUG2",
        "timestamp": msg.fecha_mensaje.isoformat(),
        "unread_delta": 1,
        "correlation_id": "{correlation_id}"
    }}
}}

bus = get_event_bus()
event = bus.publish("message.created", event_data)
print(event.id)
time.sleep(0.1)
'''
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    for line in result.stdout.split('\n'):
        if line and line[0].isdigit() and '-' in line:
            return line.strip()
    return ''


async def test():
    """Debug v2: Cache busting."""
    print("\nDEBUG v2: With cache busting...")

    sessionid = await http_login()
    corr_id = f"debug2-{uuid.uuid4().hex[:8]}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await ctx.new_page()

        # Clear all caches
        await page.evaluate('() => window.location.reload(true)')  # Hard reload
        await asyncio.sleep(1)

        # Capture logs
        logs = []
        page.on('console', lambda msg: logs.append(msg.text))

        # Navigate with cache buster
        cache_buster = int(time.time() * 1000)
        await page.goto(f'http://localhost:8001/dashboard/?v={cache_buster}', wait_until='domcontentloaded')
        await asyncio.sleep(3)

        print(f"\n[LOGS DURING INIT] {len(logs)} messages")
        for log in logs[-15:]:
            if any(x in log for x in ['REALTIME', 'eventStore', 'subscribe', 'SSE']):
                print(f"  {log[:120]}")

        logs_before = len(logs)

        # Get cursor
        c1 = await page.evaluate("""
        async () => {
          const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
          const data = await resp.json();
          return data.snapshot_cursor;
        }
        """)
        print(f"\n[CURSOR] {c1}")

        await asyncio.sleep(1)

        # Publish
        e1_id = await publish_event(corr_id)
        print(f"[EVENT] {e1_id}")

        # Wait
        await asyncio.sleep(5)

        new_logs = logs[logs_before:]

        print(f"\n[LOGS AFTER] {len(new_logs)} new messages")
        found_subscribe = False
        found_process = False

        for log in new_logs:
            full = log
            if 'subscribe' in log:
                found_subscribe = True
                print(f"  [SUBSCRIBE] {log[:120]}")
            if 'processEvent' in log or 'process' in log:
                found_process = True
                print(f"  [PROCESS] {log[:120]}")
            if 'eventStore' in log:
                print(f"  [STORE] {log[:120]}")
            if 'message.created' in log:
                print(f"  [MSG] {log[:120]}")

        print(f"\nSubscribe called: {found_subscribe}")
        print(f"ProcessEvent called: {found_process}")

        await ctx.close()
        await browser.close()


if __name__ == '__main__':
    asyncio.run(test())
