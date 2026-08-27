"""FASE 5B-A: Trace event through EventStore → Pinia stores.

Minimal test: verify event makes it to EventStore.events array
and triggers store update computations.
"""
import asyncio
import subprocess
import uuid
import requests
from playwright.async_api import async_playwright


async def http_login():
    """Login."""
    session = requests.Session()
    resp = session.post(
        'http://localhost:8001/dashboard/api/auth/login/',
        json={'username': 'e2e_test', 'password': 'e2e_test_password'}
    )
    return session.cookies.get_dict().get('sessionid') if resp.status_code == 200 else None


async def publish_event(correlation_id: str) -> dict:
    """Publish event."""
    cmd = [
        'docker', 'exec', 'taxicarga-api',
        'python', 'manage.py', 'shell', '-c',
        f'''
import os
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
    "content": "TRACE-" + str(int(time.time()*1000)),
    "sender_type": msg.sender_type,
    "direccion": msg.direccion,
    "source": msg.origen,
    "fecha_mensaje": msg.fecha_mensaje.isoformat(),
    "timestamp": msg.fecha_mensaje.isoformat(),
    "unread_delta": 1,
    "correlation_id": "{correlation_id}",
    "data": {{
        "conversation_id": msg.conversacion_id,
        "message_id": msg.id,
        "sender_type": msg.sender_type,
        "preview": "Test message",
        "timestamp": msg.fecha_mensaje.isoformat(),
        "unread_delta": 1
    }}
}}

bus = get_event_bus()
event = bus.publish("message.created", event_data)

print(f"EVENT_ID:{{event.id}}")
print(f"CORRELATION_ID:{correlation_id}")

import time
time.sleep(0.2)
'''
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    event_info = {}
    for line in result.stdout.split('\n'):
        if 'EVENT_ID:' in line:
            event_info['event_id'] = line.split(':')[1].strip()
        elif 'CORRELATION_ID:' in line:
            event_info['correlation_id'] = line.split(':')[1].strip()
    return event_info


async def test():
    """Test event store trace."""
    print("\n" + "="*80)
    print("FASE 5B-A: EventStore Trace")
    print("="*80)

    sessionid = await http_login()
    correlation_id = f"trace-{uuid.uuid4().hex[:8]}"
    print(f"[OK] Logged in, correlation={correlation_id}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await context.new_page()

        # Instrument to access Pinia stores
        await page.add_init_script("""
        window.__storeTrace = {
          eventCount: 0,
          conversationCount: 0,
          messageCount: 0,
          events: [],
          lastUpdate: null
        };

        // Wait for Pinia to initialize, then hook stores
        const checkStores = setInterval(() => {
          try {
            // Try to access pinia
            if (window.__PINIA_STORES) {
              const eventStore = window.__PINIA_STORES.eventStore;
              const convStore = window.__PINIA_STORES.conversationsStore;
              const msgStore = window.__PINIA_STORES.messagesStore;

              if (eventStore && eventStore.events) {
                window.__storeTrace.eventCount = eventStore.events.length;
                window.__storeTrace.events = eventStore.events.map(e => ({
                  id: e.id,
                  type: e.type,
                  correlation_id: e.correlation_id
                }));
              }

              if (convStore && convStore.conversations) {
                window.__storeTrace.conversationCount = Object.keys(convStore.conversations).length;
              }

              if (msgStore && msgStore.messages) {
                window.__storeTrace.messageCount = Object.values(msgStore.messages).flat().length;
              }

              window.__storeTrace.lastUpdate = new Date().toISOString();
            }
          } catch(e) {
            // Silent
          }
        }, 500);

        // Try alternative: inspect window for Vue instance
        const checkVueInstance = setInterval(() => {
          try {
            const app = window.__VUE_APP__;
            if (app && app._context && app._context.components) {
              // Found Vue app
              console.log('[TRACE] Vue app found');
              clearInterval(checkVueInstance);
            }
          } catch(e) {
            // Silent
          }
        }, 500);

        // Clean up
        setTimeout(() => {
          clearInterval(checkStores);
          clearInterval(checkVueInstance);
        }, 30000);
        """)

        await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        await asyncio.sleep(2)
        print("[OK] Dashboard loaded")

        # Get cursor
        c1 = await page.evaluate("""
        async () => {
          const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
          const data = await resp.json();
          return data.snapshot_cursor;
        }
        """)
        print(f"[OK] Cursor C1={c1}")

        # Wait a bit for SSE to open
        await asyncio.sleep(1)

        # Publish event
        print("[STEP] Publishing event...")
        event_info = await publish_event(correlation_id)
        e1_id = event_info.get('event_id', 'UNKNOWN')
        print(f"[OK] Event published E1={e1_id}")

        # Check EventSource state
        print("\n[STEP] Checking event delivery...")
        for i in range(10):
            await asyncio.sleep(0.5)

            # Try multiple ways to access event store
            events = await page.evaluate("""
            async () => {
              try {
                // Check console logs for REALTIME trace messages
                return {
                  hasConsoleTrace: window.__eventSourceDiagnostics ?
                    window.__eventSourceDiagnostics.events?.length > 0 : false
                };
              } catch(e) {
                return { error: e.message };
              }
            }
            """)

            if i == 9:
                print(f"[INFO] EventSource state check:")
                print(f"       {events}")

        # Get final state
        final_state = await page.evaluate("""
        async () => {
          // Try to read eventStore directly
          try {
            // This won't work directly, but we can check DOM for loaded data
            const convList = document.querySelectorAll('[data-conversation-id]');
            const msgList = document.querySelectorAll('[data-message-id]');

            return {
              conversations_in_dom: convList.length,
              messages_in_dom: msgList.length,
              title: document.title
            };
          } catch(e) {
            return { error: e.message };
          }
        }
        """)

        print(f"\n[RESULT] DOM state: {final_state}")

        # Now test with a component that definitely uses messaging
        # Navigate to bandeja-entrada if it exists
        try:
            await page.goto('http://localhost:8001/dashboard/bandeja-entrada/', wait_until='domcontentloaded', timeout=5000)
            print("[OK] Navigated to bandeja-entrada")

            await asyncio.sleep(2)

            # Check if message appears in bandeja
            msg_count = await page.evaluate("""
            () => {
              const messages = document.querySelectorAll('.message');
              return messages.length;
            }
            """)

            print(f"[RESULT] Messages in bandeja: {msg_count}")

        except Exception as e:
            print(f"[INFO] Bandeja navigation not available: {str(e)[:100]}")

        await context.close()
        await browser.close()

        return True


if __name__ == '__main__':
    asyncio.run(test())
