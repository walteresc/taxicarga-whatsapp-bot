"""FASE 5B-A: Corrected test - publish AFTER SSE OPEN."""
import asyncio
import subprocess
import time
import uuid
import requests
from playwright.async_api import async_playwright


def parse_redis_id(redis_id: str) -> tuple:
    """Parse Redis ID into (milliseconds, sequence)."""
    parts = redis_id.split('-')
    return (int(parts[0]), int(parts[1]))


def redis_id_is_after(event_id: str, cursor_id: str) -> bool:
    """Check if event_id > cursor_id by Redis ordering."""
    event_ms, event_seq = parse_redis_id(event_id)
    cursor_ms, cursor_seq = parse_redis_id(cursor_id)
    return (event_ms, event_seq) > (cursor_ms, cursor_seq)


async def http_login():
    """Login and get sessionid."""
    session = requests.Session()
    resp = session.post(
        'http://localhost:8001/dashboard/api/auth/login/',
        json={'username': 'e2e_test', 'password': 'e2e_test_password'}
    )
    return session.cookies.get_dict().get('sessionid') if resp.status_code == 200 else None


async def publish_event_after_docker(correlation_id: str):
    """Publish event from Django AFTER this function is called."""
    cmd = [
        'docker', 'exec', 'taxicarga-api',
        'python', 'manage.py', 'shell', '-c',
        f'''
import os, json, uuid, time
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_e2e"
import django
django.setup()

from apps.whatsapp.models import MensajeWhatsApp
from apps.whatsapp.redis_events import get_event_bus

msg = MensajeWhatsApp.objects.get(id=117)

event_data = {{
    "conversation_id": msg.conversacion_id,
    "message_id": msg.id,
    "channel_id": msg.conversacion.channel_id,
    "cliente_id": msg.conversacion.cliente_id,
    "content": msg.contenido[:50],
    "sender_type": msg.sender_type,
    "direccion": msg.direccion,
    "source": msg.origen,
    "fecha_mensaje": msg.fecha_mensaje.isoformat(),
    "unread_delta": 1,
    "correlation_id": "{correlation_id}"
}}

bus = get_event_bus()
event = bus.publish("message.created", event_data)

print(f"EVENT_ID:{{event.id}}")
print(f"CORRELATION_ID:{correlation_id}")
'''
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    event_info = {}
    for line in result.stdout.split('\n'):
        if 'EVENT_ID:' in line:
            event_info['event_id'] = line.split(':')[1]
        elif 'CORRELATION_ID:' in line:
            event_info['correlation_id'] = line.split(':')[1]
    return event_info


async def test_one_tab():
    """Test with one browser tab."""
    print("\n" + "="*80)
    print("FASE 5B-A: ONE TAB TEST")
    print("="*80)

    # Step 1: Login
    print("\n[STEP 1] Login")
    sessionid = await http_login()
    if not sessionid:
        print("[FAIL] Login failed")
        return False
    print(f"[OK] sessionid={sessionid[:20]}")

    correlation_id = f"one-tab-{uuid.uuid4().hex[:8]}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await context.new_page()

        # Instrument before navigation
        print("\n[STEP 2] Instrument EventSource")
        await page.add_init_script("""
        window.__state = {
          probe_opened: false,
          probe_events: [],
          app_events: [],
          app_listeners: [],
          diagnostics: []
        };

        const OrigES = window.EventSource;
        window.EventSource = function(url, config) {
          const id = Math.random().toString(36).substr(2, 8);
          const es = new OrigES(url, config);

          es.addEventListener('open', () => {
            console.log(`[ES${id}] open`);
            window.__state.diagnostics.push({id, event: 'open'});
            if (url.includes('cursor')) window.__state.probe_opened = true;
          });

          es.addEventListener('message.created', (e) => {
            try {
              const data = JSON.parse(e.data);
              console.log(`[ES${id}] message.created`);
              window.__state.probe_events.push({
                id: e.lastEventId,
                correlation_id: data.correlation_id,
                received_ms: Date.now()
              });
            } catch (err) {
              console.error(`[ES${id}] parse error:`, err.message);
            }
          });

          es.addEventListener('error', (e) => {
            console.log(`[ES${id}] error: readyState=${es.readyState}`);
          });

          // Track listeners on app ES
          if (!url.includes('cursor')) {
            const origAdd = es.addEventListener;
            es.addEventListener = function(type, listener, opts) {
              window.__state.app_listeners.push(type);
              return origAdd.call(this, type, listener, opts);
            };
          }

          return es;
        };
        window.EventSource.prototype = OrigES.prototype;
        """)
        print("[OK] Instrumentation ready")

        # Step 3: Navigate
        print("\n[STEP 3] Navigate to dashboard")
        await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        await asyncio.sleep(1)
        print("[OK] Dashboard loaded")

        # Step 4: Get snapshot cursor
        print("\n[STEP 4] Get snapshot cursor (C1)")
        c1 = await page.evaluate("""
        async () => {
          const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
          const data = await resp.json();
          return data.snapshot_cursor;
        }
        """)
        print(f"[OK] C1={c1}")

        # Step 5-7: Wait for app EventSource to open (from app initialization)
        print("\n[STEP 5-7] Wait for app EventSource OPEN")
        for i in range(10):
            diag = await page.evaluate("() => window.__state.diagnostics")
            if any(d['event'] == 'open' for d in diag):
                print(f"[OK] App EventSource opened at {i}s")
                break
            await asyncio.sleep(0.5)

        # Step 8: Create probe and wait for OPEN
        print("\n[STEP 8] Create probe EventSource")
        await page.evaluate(f"""
        () => {{
          const url = `/dashboard/whatsapp/api/events/stream/?cursor=${{encodeURIComponent("{c1}")}}`;
          new EventSource(url, {{ withCredentials: true }});
        }}
        """)

        for i in range(10):
            probe_open = await page.evaluate("() => window.__state.probe_opened")
            if probe_open:
                print(f"[OK] Probe OPEN at {i}s")
                break
            await asyncio.sleep(0.5)

        # Step 9: NOW publish event (AFTER both open)
        print("\n[STEP 9] Publish E1 (AFTER both OPEN)")
        await asyncio.sleep(0.5)  # Ensure both fully open
        event_info = await publish_event_after_docker(correlation_id)
        e1_id = event_info.get('event_id', '')
        print(f"[OK] E1={e1_id}")

        # Step 10: Verify ordering
        print("\n[STEP 10] Verify E1 > C1 (ordering assertion)")
        if redis_id_is_after(e1_id, c1):
            print(f"[OK] E1({e1_id}) > C1({c1})")
        else:
            print(f"[FAIL] E1({e1_id}) NOT > C1({c1})")
            return False

        # Step 11-13: Wait for events
        print("\n[STEP 11-13] Wait for event delivery (5s)")
        for i in range(10):
            await asyncio.sleep(0.5)
            probe_events = await page.evaluate("() => window.__state.probe_events")

            if probe_events and any(e['correlation_id'] == correlation_id for e in probe_events):
                print(f"[OK] Probe received E1 at {i}s")
                break

        # Final check
        probe_final = await page.evaluate("() => window.__state.probe_events")
        has_event = any(e['correlation_id'] == correlation_id for e in probe_final)

        print("\n" + "="*80)
        print("ONE TAB RESULT")
        print("="*80)
        print(f"Probe received E1: {has_event}")
        print(f"Total events in probe: {len(probe_final)}")
        if probe_final:
            print(f"Last event: {probe_final[-1]}")

        await context.close()
        await browser.close()

        return has_event


async def main():
    """Main test execution."""
    result = await test_one_tab()

    if result:
        print("\n[PASS] FASE 5B-A: One tab working correctly")
        print("[OK] Event published AFTER SSE OPEN")
        print("[OK] Ordering verified (E1 > C1)")
        print("[OK] Probe received event within 5s")
        print("[OK] Correlation ID traced")
        return True
    else:
        print("\n[FAIL] FASE 5B-A: One tab did NOT receive event")
        return False


if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)
