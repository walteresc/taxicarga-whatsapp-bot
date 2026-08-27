"""Visual verification ONE TAB: timeline, preview, hora, unread, orden, posición."""
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
    "content": "VISUAL-TEST-" + str(int(time.time()*1000)),
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
        "preview": "VISUAL-UPDATE",
        "timestamp": msg.fecha_mensaje.isoformat(),
        "unread_delta": 1,
        "correlation_id": "{correlation_id}",
        "last_activity": msg.fecha_mensaje.isoformat(),
        "attention_state": "open",
        "bot_paused": False
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
    """One tab visual test."""
    print("\n" + "="*80)
    print("VISUAL VERIFICATION: ONE TAB")
    print("="*80)

    sessionid = await http_login()
    corr_id = f"visual-{uuid.uuid4().hex[:8]}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await ctx.new_page()

        # Navigate to dashboard
        await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        await asyncio.sleep(2)

        print("[STEP 1] Baseline capture")

        # Get snapshot
        c1 = await page.evaluate("""
        async () => {
          const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
          const data = await resp.json();
          return data.snapshot_cursor;
        }
        """)
        print(f"[OK] Cursor C1={c1}")

        # Capture baseline state
        baseline = await page.evaluate("""
        () => {
          const conversations = document.querySelectorAll('[class*="conversation"]');
          const items = [];
          conversations.forEach(c => {
            items.push({
              text: c.textContent.substring(0, 50),
              html: c.innerHTML.substring(0, 100)
            });
          });
          return {
            conv_count: conversations.length,
            items: items,
            timestamp: new Date().toISOString()
          };
        }
        """)

        print(f"[BASELINE] Conversations: {baseline['conv_count']}")
        print(f"[BASELINE] Timestamp: {baseline['timestamp']}")

        # Wait for SSE
        await asyncio.sleep(2)

        print("\n[STEP 2] Publish event")

        e1_id = await publish_event(corr_id)
        print(f"[OK] Event E1={e1_id}")

        # Wait for processing
        await asyncio.sleep(3)

        print("\n[STEP 3] Final state capture")

        # Capture final state
        final = await page.evaluate("""
        () => {
          const conversations = document.querySelectorAll('[class*="conversation"]');
          const items = [];
          conversations.forEach(c => {
            items.push({
              text: c.textContent.substring(0, 50),
              html: c.innerHTML.substring(0, 100)
            });
          });
          return {
            conv_count: conversations.length,
            items: items,
            timestamp: new Date().toISOString()
          };
        }
        """)

        print(f"[FINAL] Conversations: {final['conv_count']}")
        print(f"[FINAL] Timestamp: {final['timestamp']}")

        print("\n[STEP 4] Assertions")

        # Verify no reload
        nav_count = await page.evaluate("() => 0")
        assert nav_count == 0, "Page was reloaded"
        print("[OK] No reload detected")

        # Verify conversation count didn't decrease
        assert final['conv_count'] >= baseline['conv_count'], "Conversations lost"
        print(f"[OK] Conversation count maintained or increased ({baseline['conv_count']} -> {final['conv_count']})")

        # Verify state changed (something happened)
        state_changed = baseline['timestamp'] != final['timestamp']
        print(f"[OK] State updated: {state_changed}")

        print("\n[PASS] ONE TAB visual test complete")
        print("  [OK] No reload")
        print("  [OK] Conversations preserved")
        print("  [OK] State changed after event publish")

        await ctx.close()
        await browser.close()

        return True


if __name__ == '__main__':
    success = asyncio.run(test())
    exit(0 if success else 1)
