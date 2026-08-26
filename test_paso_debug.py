"""Debug: verificar qué logs genera el frontend."""
import asyncio
import subprocess
import uuid
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
    "content": "DEBUG-TEST",
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
        "preview": "DEBUG",
        "timestamp": msg.fecha_mensaje.isoformat(),
        "unread_delta": 1,
        "correlation_id": "{correlation_id}"
    }}
}}

bus = get_event_bus()
event = bus.publish("message.created", event_data)
print(event.id)
time.sleep(0.2)
'''
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    for line in result.stdout.split('\n'):
        if line and line[0].isdigit() and '-' in line:
            return line.strip()
    return ''


async def test():
    """Debug: Capture ALL console logs."""
    print("\nDEBUG: Capturing console logs...")

    sessionid = await http_login()
    corr_id = f"debug-{uuid.uuid4().hex[:8]}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await ctx.new_page()

        # Capture ALL console logs
        logs = []
        page.on('console', lambda msg: logs.append(msg.text))

        # Navigate
        await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        await asyncio.sleep(3)

        print(f"\n[LOGS DURING INIT] {len(logs)} messages")
        for log in logs[-10:]:
            if 'REALTIME' in log or 'eventStore' in log or 'subscribe' in log:
                print(f"  {log[:120]}")

        # Get cursor
        c1 = await page.evaluate("""
        async () => {
          const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
          const data = await resp.json();
          return data.snapshot_cursor;
        }
        """)
        print(f"\n[CURSOR] {c1}")

        logs_before_publish = len(logs)

        # Publish
        await asyncio.sleep(1)
        e1_id = await publish_event(corr_id)
        print(f"[EVENT PUBLISHED] {e1_id}")

        # Wait and collect logs
        await asyncio.sleep(5)

        logs_after = logs[logs_before_publish:]

        print(f"\n[LOGS AFTER PUBLISH] {len(logs_after)} new messages")
        for log in logs_after:
            if 'REALTIME' in log or 'eventStore' in log or 'subscribe' in log or 'processEvent' in log or corr_id in log:
                print(f"  {log[:150]}")

        if not any('eventStore' in log for log in logs_after):
            print("  [NO eventStore LOGS]")

        if not any('subscribe' in log for log in logs_after):
            print("  [NO subscribe LOGS]")

        if not any('processEvent' in log for log in logs_after):
            print("  [NO processEvent LOGS]")

        await ctx.close()
        await browser.close()


if __name__ == '__main__':
    asyncio.run(test())
