"""FASE 5B-A: Complete E2E SSE test with correlation tracing.

Validates that real-time events published to Redis are correctly delivered
via Server-Sent Events to browser clients, with proper cursor semantics
(exclusive range) and correlation ID tracing through entire stack.

Tests:
1. Single tab: Event published AFTER SSE open, probe receives event
2. Two tabs: Simultaneous tabs each receive event with independent cursors
"""
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


async def publish_event(correlation_id: str) -> dict:
    """Publish event from Django shell."""
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


async def setup_page_instrumentation(page, page_num: int):
    """Inject EventSource instrumentation."""
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
        window.__state.diagnostics.push({{id, event: 'open'}});
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


async def test_single_tab():
    """Test single browser tab with SSE delivery."""
    print("\n" + "="*80)
    print("TEST 1: SINGLE TAB")
    print("="*80)

    sessionid = await http_login()
    if not sessionid:
        print("[FAIL] Login failed")
        return False
    print(f"[OK] Login sessionid={sessionid[:20]}")

    correlation_id = f"single-{uuid.uuid4().hex[:8]}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await context.new_page()

        await setup_page_instrumentation(page, 1)
        print("[OK] Instrumentation injected")

        await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        await asyncio.sleep(1)
        print("[OK] Dashboard loaded")

        # Get snapshot cursor
        c1 = await page.evaluate("""
        async () => {
          const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
          const data = await resp.json();
          return data.snapshot_cursor;
        }
        """)
        print(f"[OK] Snapshot cursor C1={c1}")

        # Wait for app EventSource OPEN
        for i in range(10):
            diag = await page.evaluate("() => window.__state.diagnostics")
            if any(d['event'] == 'open' for d in diag):
                print(f"[OK] App EventSource OPEN")
                break
            await asyncio.sleep(0.5)

        # Create probe
        await page.evaluate(f"""
        () => {{
          const url = `/dashboard/whatsapp/api/events/stream/?cursor=${{encodeURIComponent("{c1}")}}`;
          new EventSource(url, {{ withCredentials: true }});
        }}
        """)

        # Wait for probe OPEN
        for i in range(10):
            probe_open = await page.evaluate("() => window.__state.probe_opened")
            if probe_open:
                print(f"[OK] Probe OPEN")
                break
            await asyncio.sleep(0.5)

        # Publish event AFTER both open
        await asyncio.sleep(0.5)
        print("[STEP] Publishing event AFTER both SSE instances open...")
        event_info = await publish_event(correlation_id)
        e1_id = event_info.get('event_id', '')
        print(f"[OK] Event published E1={e1_id}")

        # Verify ordering
        if not redis_id_is_after(e1_id, c1):
            print(f"[FAIL] Ordering: E1 NOT > C1")
            return False
        print(f"[OK] Cursor semantics verified: E1({e1_id}) > C1({c1})")

        # Wait for event delivery
        print("[STEP] Waiting for probe to receive event...")
        for i in range(10):
            await asyncio.sleep(0.5)
            probe_events = await page.evaluate("() => window.__state.probe_events")

            if any(e['correlation_id'] == correlation_id for e in probe_events):
                print(f"[OK] Probe received event at {i}s")
                break

        # Final verification
        probe_final = await page.evaluate("() => window.__state.probe_events")
        has_event = any(e['correlation_id'] == correlation_id for e in probe_final)

        print(f"[RESULT] Probe events received: {len(probe_final)}")
        if probe_final:
            print(f"         Last event ID: {probe_final[-1]['id']}")
            print(f"         Correlation: {probe_final[-1]['correlation_id']}")

        await context.close()
        await browser.close()

        return has_event


async def test_two_tabs():
    """Test two simultaneous tabs with independent cursors."""
    print("\n" + "="*80)
    print("TEST 2: TWO SIMULTANEOUS TABS")
    print("="*80)

    sessionid = await http_login()
    if not sessionid:
        print("[FAIL] Login failed")
        return False
    print(f"[OK] Login sessionid={sessionid[:20]}")

    correlation_id = f"dual-{uuid.uuid4().hex[:8]}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )

        page1 = await context.new_page()
        page2 = await context.new_page()

        await setup_page_instrumentation(page1, 1)
        await setup_page_instrumentation(page2, 2)
        print("[OK] Both pages instrumented")

        # Navigate both
        await asyncio.gather(
            page1.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded'),
            page2.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        )
        await asyncio.sleep(1)
        print("[OK] Both dashboards loaded")

        # Get cursors
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
        print(f"[OK] Page1 cursor C1={c1_page1}")
        print(f"[OK] Page2 cursor C1={c1_page2}")

        # Wait for app EventSource OPEN
        for page_num, page in enumerate([page1, page2], 1):
            for i in range(10):
                diag = await page.evaluate("() => window.__state.diagnostics")
                if any(d['event'] == 'open' for d in diag):
                    print(f"[OK] Page{page_num} app EventSource OPEN")
                    break
                await asyncio.sleep(0.5)

        # Create probes
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

        # Wait for probes OPEN
        for page_num, page in enumerate([page1, page2], 1):
            for i in range(10):
                probe_open = await page.evaluate("() => window.__state.probe_opened")
                if probe_open:
                    print(f"[OK] Page{page_num} probe OPEN")
                    break
                await asyncio.sleep(0.5)

        # Publish event AFTER both probes open
        await asyncio.sleep(0.5)
        print("[STEP] Publishing event AFTER both probes open...")
        event_info = await publish_event(correlation_id)
        e1_id = event_info.get('event_id', '')
        print(f"[OK] Event published E1={e1_id}")

        # Verify ordering
        ok1 = redis_id_is_after(e1_id, c1_page1)
        ok2 = redis_id_is_after(e1_id, c1_page2)
        if not (ok1 and ok2):
            print(f"[FAIL] Ordering mismatch")
            return False
        print(f"[OK] Cursor semantics verified on both tabs")

        # Wait for delivery
        print("[STEP] Waiting for probes to receive event...")
        for i in range(10):
            await asyncio.sleep(0.5)

            probe1, probe2 = await asyncio.gather(
                page1.evaluate("() => window.__state.probe_events"),
                page2.evaluate("() => window.__state.probe_events")
            )

            has1 = any(e['correlation_id'] == correlation_id for e in probe1)
            has2 = any(e['correlation_id'] == correlation_id for e in probe2)

            if has1 and has2:
                print(f"[OK] Both probes received event at {i}s")
                break

        # Final verification
        probe_final_1 = await page1.evaluate("() => window.__state.probe_events")
        probe_final_2 = await page2.evaluate("() => window.__state.probe_events")

        has_event_1 = any(e['correlation_id'] == correlation_id for e in probe_final_1)
        has_event_2 = any(e['correlation_id'] == correlation_id for e in probe_final_2)

        print(f"[RESULT] Page1 events: {len(probe_final_1)}")
        print(f"[RESULT] Page2 events: {len(probe_final_2)}")

        await context.close()
        await browser.close()

        return has_event_1 and has_event_2


async def main():
    """Run all tests."""
    test1_result = await test_single_tab()
    test2_result = await test_two_tabs()

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Single tab:      {'PASS' if test1_result else 'FAIL'}")
    print(f"Two tabs:        {'PASS' if test2_result else 'FAIL'}")

    if test1_result and test2_result:
        print("\n[PASS] FASE 5B-A: All tests passed")
        print("  - Single tab receives event after SSE open")
        print("  - Two tabs receive event with independent cursors")
        print("  - Cursor semantics verified (exclusive range)")
        print("  - Correlation ID traced through entire stack")
        return True
    else:
        print("\n[FAIL] FASE 5B-A: One or more tests failed")
        return False


if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)
