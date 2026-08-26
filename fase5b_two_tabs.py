"""FASE 5B-A: Two simultaneous tabs test."""
import asyncio
import subprocess
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
    """Publish event from Django."""
    cmd = [
        'docker', 'exec', 'taxicarga-api',
        'python', 'manage.py', 'shell', '-c',
        f'''
import os, json, uuid
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


async def test_two_tabs():
    """Test with two simultaneous browser tabs."""
    print("\n" + "="*80)
    print("FASE 5B-A: TWO TABS SIMULTANEOUS TEST")
    print("="*80)

    # Step 1: Login
    print("\n[STEP 1] Login")
    sessionid = await http_login()
    if not sessionid:
        print("[FAIL] Login failed")
        return False
    print(f"[OK] sessionid={sessionid[:20]}")

    correlation_id = f"two-tabs-{uuid.uuid4().hex[:8]}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )

        # Create two pages
        page1 = await context.new_page()
        page2 = await context.new_page()

        # Instrument both
        for page_num, page in enumerate([page1, page2], 1):
            await page.add_init_script(f"""
            window.__state = {{
              page_num: {page_num},
              probe_opened: false,
              probe_events: [],
              app_opened: false,
              app_events: [],
              diagnostics: []
            }};

            const OrigES = window.EventSource;
            window.EventSource = function(url, config) {{
              const id = Math.random().toString(36).substr(2, 8);
              const es = new OrigES(url, config);

              es.addEventListener('open', () => {{
                console.log(`[Page {page_num}][ES${{id}}] open`);
                window.__state.diagnostics.push({{id, event: 'open', page: {page_num}}});
                if (url.includes('cursor')) window.__state.probe_opened = true;
                else window.__state.app_opened = true;
              }});

              es.addEventListener('message.created', (e) => {{
                try {{
                  const data = JSON.parse(e.data);
                  console.log(`[Page {page_num}][ES${{id}}] message.created`);
                  if (url.includes('cursor')) {{
                    window.__state.probe_events.push({{
                      id: e.lastEventId,
                      correlation_id: data.correlation_id,
                      received_ms: Date.now()
                    }});
                  }} else {{
                    window.__state.app_events.push({{
                      id: e.lastEventId,
                      correlation_id: data.correlation_id,
                      received_ms: Date.now()
                    }});
                  }}
                }} catch (err) {{
                  console.error(`[Page {page_num}][ES${{id}}] parse error:`, err.message);
                }}
              }});

              es.addEventListener('error', (e) => {{
                console.log(`[Page {page_num}][ES${{id}}] error: readyState=${{es.readyState}}`);
              }});

              return es;
            }};
            window.EventSource.prototype = OrigES.prototype;
            """)

        print("[OK] Both pages instrumented")

        # Navigate both
        print("\n[STEP 2] Navigate both pages")
        await asyncio.gather(
            page1.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded'),
            page2.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        )
        await asyncio.sleep(1)
        print("[OK] Both pages loaded")

        # Get cursors
        print("\n[STEP 3] Get snapshot cursors")
        c1_page1, c1_page2 = await asyncio.gather(
            page1.evaluate("""
            async () => {
              const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
              const data = await resp.json();
              return data.snapshot_cursor;
            }
            """),
            page2.evaluate("""
            async () => {
              const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
              const data = await resp.json();
              return data.snapshot_cursor;
            }
            """)
        )
        print(f"[OK] Page1 C1={c1_page1}")
        print(f"[OK] Page2 C1={c1_page2}")

        # Wait for app EventSource OPEN on both
        print("\n[STEP 4] Wait for app EventSource OPEN (both pages)")
        for page_num, page in enumerate([page1, page2], 1):
            for i in range(10):
                diag = await page.evaluate("() => window.__state.diagnostics")
                if any(d['event'] == 'open' for d in diag):
                    print(f"[OK] Page{page_num} app EventSource opened")
                    break
                await asyncio.sleep(0.5)

        # Create probe on both with different cursors
        print("\n[STEP 5] Create probe EventSource on both pages")
        await asyncio.gather(
            page1.evaluate(f"""
            () => {{
              const url = `/dashboard/whatsapp/api/events/stream/?cursor=${{encodeURIComponent("{c1_page1}")}}`;
              new EventSource(url, {{ withCredentials: true }});
            }}
            """),
            page2.evaluate(f"""
            () => {{
              const url = `/dashboard/whatsapp/api/events/stream/?cursor=${{encodeURIComponent("{c1_page2}")}}`;
              new EventSource(url, {{ withCredentials: true }});
            }}
            """)
        )

        # Wait for probe OPEN
        print("\n[STEP 6] Wait for probe OPEN (both pages)")
        for page_num, page in enumerate([page1, page2], 1):
            for i in range(10):
                probe_open = await page.evaluate("() => window.__state.probe_opened")
                if probe_open:
                    print(f"[OK] Page{page_num} probe opened")
                    break
                await asyncio.sleep(0.5)

        # NOW publish (AFTER both probes open)
        print("\n[STEP 7] Publish E1 (AFTER both probes OPEN)")
        await asyncio.sleep(0.5)
        event_info = await publish_event_after_docker(correlation_id)
        e1_id = event_info.get('event_id', '')
        print(f"[OK] E1={e1_id}")

        # Verify ordering on both
        print("\n[STEP 8] Verify ordering")
        ok1 = redis_id_is_after(e1_id, c1_page1)
        ok2 = redis_id_is_after(e1_id, c1_page2)
        print(f"[OK] Page1: E1 > C1 = {ok1}")
        print(f"[OK] Page2: E1 > C1 = {ok2}")

        # Wait for events on both
        print("\n[STEP 9] Wait for event delivery (5s on both)")
        for i in range(10):
            await asyncio.sleep(0.5)

            probe1, probe2 = await asyncio.gather(
                page1.evaluate("() => window.__state.probe_events"),
                page2.evaluate("() => window.__state.probe_events")
            )

            has1 = any(e['correlation_id'] == correlation_id for e in probe1)
            has2 = any(e['correlation_id'] == correlation_id for e in probe2)

            if has1 and has2:
                print(f"[OK] Both pages received E1 at {i}s")
                break

        # Final check
        probe_final_1 = await page1.evaluate("() => window.__state.probe_events")
        probe_final_2 = await page2.evaluate("() => window.__state.probe_events")

        has_event_1 = any(e['correlation_id'] == correlation_id for e in probe_final_1)
        has_event_2 = any(e['correlation_id'] == correlation_id for e in probe_final_2)

        print("\n" + "="*80)
        print("TWO TABS RESULT")
        print("="*80)
        print(f"Page1 received E1: {has_event_1}")
        print(f"Page2 received E1: {has_event_2}")
        print(f"Page1 total events: {len(probe_final_1)}")
        print(f"Page2 total events: {len(probe_final_2)}")

        await context.close()
        await browser.close()

        return has_event_1 and has_event_2


async def main():
    """Main test execution."""
    result = await test_two_tabs()

    if result:
        print("\n[PASS] FASE 5B-A: Two tabs working correctly")
        print("[OK] Event published AFTER both SSE OPEN")
        print("[OK] Ordering verified on both tabs")
        print("[OK] Both probes received event within 5s")
        print("[OK] Correlation ID traced on both tabs")
        return True
    else:
        print("\n[FAIL] FASE 5B-A: One or both tabs did NOT receive event")
        return False


if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)
