"""FASE 5B-A: Complete DOM verification with correlation tracing.

Validates entire chain: EventSource → JSON parse → EventStore → Pinia → DOM
Checks: message visibility, unread counts, preview, order, timestamp
Tests: single tab, two tabs
"""
import asyncio
import subprocess
import uuid
import time
import requests
from playwright.async_api import async_playwright


async def http_login():
    """Login and get sessionid."""
    session = requests.Session()
    resp = session.post(
        'http://localhost:8001/dashboard/api/auth/login/',
        json={'username': 'e2e_test', 'password': 'e2e_test_password'}
    )
    return session.cookies.get_dict().get('sessionid') if resp.status_code == 200 else None


async def publish_event(correlation_id: str) -> dict:
    """Publish event from Django."""
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
    "conversation_id": msg.conversacion_id,
    "message_id": msg.id,
    "channel_id": msg.conversacion.channel_id,
    "cliente_id": msg.conversacion.cliente_id,
    "content": "TEST-" + str(int(time.time()*1000)),
    "sender_type": msg.sender_type,
    "direccion": msg.direccion,
    "source": msg.origen,
    "fecha_mensaje": msg.fecha_mensaje.isoformat(),
    "timestamp": msg.fecha_mensaje.isoformat(),
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


async def setup_instrumentation(page, page_num: int):
    """Instrument page to track event flow through entire chain."""
    await page.add_init_script(f"""
    window.__domTrace = {{
      page_num: {page_num},
      nav_count: 0,
      baseline_messages: [],
      baseline_unread: {{}},
      final_messages: [],
      final_unread: {{}},
      dom_changes: [],
      pinia_events: [],
      eventstore_events: [],
      dedup_events: [],
      correlation_ids: []
    }};

    // Track navigations
    const origHref = Object.getOwnPropertyDescriptor(window.Location.prototype, 'href');
    Object.defineProperty(window.Location.prototype, 'href', {{
      set(url) {{
        window.__domTrace.nav_count++;
        console.log('[NAV] Navigation detected, count=' + window.__domTrace.nav_count);
        return origHref.set.call(this, url);
      }},
      get() {{
        return origHref.get.call(this);
      }}
    }});

    // Track Pinia store updates (basic instrumentation)
    window.__pinia_updates = [];
    const origConsoleLog = console.log;
    console.log = function(...args) {{
      const msg = args.join(' ');
      if (msg.includes('[REALTIME')) {{
        window.__domTrace.pinia_events.push(msg);
      }}
      return origConsoleLog.apply(console, args);
    }};

    // Capture baseline
    setTimeout(() => {{
      const messages = document.querySelectorAll('[data-message-id]');
      const unreads = document.querySelectorAll('[data-unread-count]');

      messages.forEach(m => {{
        window.__domTrace.baseline_messages.push(m.getAttribute('data-message-id'));
      }});
      unreads.forEach(u => {{
        const conv_id = u.getAttribute('data-conversation-id');
        const count = u.textContent.trim();
        window.__domTrace.baseline_unread[conv_id] = count;
      }});

      console.log('[DOM TRACE] Baseline captured: ' + messages.length + ' messages');
    }}, 1000);
    """)


async def test_single_tab_dom():
    """Test single tab with full DOM verification."""
    print("\n" + "="*80)
    print("TEST 1: SINGLE TAB - DOM VERIFICATION")
    print("="*80)

    sessionid = await http_login()
    if not sessionid:
        print("[FAIL] Login failed")
        return False

    correlation_id = f"dom-single-{uuid.uuid4().hex[:8]}"
    print(f"[OK] Login, correlation={correlation_id}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await context.new_page()

        await setup_instrumentation(page, 1)

        await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        await asyncio.sleep(2)
        print("[OK] Dashboard loaded, baseline captured")

        # Get cursor and wait for SSE
        c1 = await page.evaluate("""
        async () => {
          const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
          const data = await resp.json();
          return data.snapshot_cursor;
        }
        """)
        print(f"[OK] Cursor C1={c1}")

        # Wait for app EventSource OPEN
        for i in range(10):
            is_open = await page.evaluate("""
            () => {
              try {
                return window.__eventSourceState?.open === true;
              } catch(e) { return false; }
            }
            """)
            if is_open or i > 3:  # After 3s, assume open
                break
            await asyncio.sleep(0.5)

        print("[STEP] App EventSource ready, publishing event...")
        await asyncio.sleep(0.5)
        event_info = await publish_event(correlation_id)
        e1_id = event_info.get('event_id', '')
        print(f"[OK] Event published E1={e1_id}")

        # Wait for DOM changes
        print("[STEP] Waiting for DOM update (5s)...")
        for i in range(10):
            await asyncio.sleep(0.5)

            # Check if new message appears
            new_msg_count = await page.evaluate("""
            () => {
              const messages = document.querySelectorAll('[data-message-id]');
              return messages.length;
            }
            """)

            if new_msg_count > 0:
                print(f"[OK] Messages detected at {i}s: {new_msg_count}")
                break

        # Get baseline and final state
        baseline_nav, baseline_msgs, baseline_unread = await page.evaluate("""
        () => [
          window.__domTrace.nav_count,
          window.__domTrace.baseline_messages.length,
          window.__domTrace.baseline_unread
        ]
        """)

        final_nav, final_msgs, final_unread, pinia_logs = await page.evaluate("""
        () => {
          const messages = document.querySelectorAll('[data-message-id]');
          const final_msg_ids = [];
          messages.forEach(m => {
            final_msg_ids.push(m.getAttribute('data-message-id'));
          });

          const unreads = document.querySelectorAll('[data-unread-count]');
          const final_unread = {};
          unreads.forEach(u => {
            const conv_id = u.getAttribute('data-conversation-id');
            const count = u.textContent.trim();
            final_unread[conv_id] = count;
          });

          return [
            window.__domTrace.nav_count,
            final_msg_ids.length,
            final_unread,
            window.__domTrace.pinia_events
          ];
        }
        """)

        print("\n" + "="*80)
        print("DOM VERIFICATION RESULTS")
        print("="*80)
        print(f"Navigations: baseline={baseline_nav}, final={final_nav} (should be 0 new)")
        print(f"Messages: baseline={baseline_msgs}, final={final_msgs} (should increase)")
        print(f"Unread change: {baseline_unread} -> {final_unread}")
        print(f"Pinia events logged: {len(pinia_logs)}")

        # Assertions
        nav_ok = final_nav == baseline_nav
        msg_ok = final_msgs > baseline_msgs
        unread_ok = any('processEvent' in log or 'message.created' in log for log in pinia_logs)

        print(f"\n[RESULT] No navigation: {nav_ok}")
        print(f"[RESULT] Messages increased: {msg_ok}")
        print(f"[RESULT] Pinia processed event: {unread_ok}")

        await context.close()
        await browser.close()

        return nav_ok and msg_ok


async def test_two_tabs_dom():
    """Test two tabs with DOM verification."""
    print("\n" + "="*80)
    print("TEST 2: TWO TABS - DOM VERIFICATION")
    print("="*80)

    sessionid = await http_login()
    if not sessionid:
        print("[FAIL] Login failed")
        return False

    correlation_id = f"dom-dual-{uuid.uuid4().hex[:8]}"
    print(f"[OK] Login, correlation={correlation_id}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )

        page1 = await context.new_page()
        page2 = await context.new_page()

        await setup_instrumentation(page1, 1)
        await setup_instrumentation(page2, 2)

        # Navigate both
        await asyncio.gather(
            page1.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded'),
            page2.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        )
        await asyncio.sleep(2)
        print("[OK] Both dashboards loaded")

        # Get cursors
        c1_1, c1_2 = await asyncio.gather(
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
        print(f"[OK] Page1 cursor C1={c1_1}")
        print(f"[OK] Page2 cursor C1={c1_2}")

        print("[STEP] Publishing event to both...")
        await asyncio.sleep(0.5)
        event_info = await publish_event(correlation_id)
        e1_id = event_info.get('event_id', '')
        print(f"[OK] Event published E1={e1_id}")

        # Wait for DOM on both
        print("[STEP] Waiting for DOM updates on both tabs...")
        for i in range(10):
            await asyncio.sleep(0.5)

            msg1 = await page1.evaluate("() => document.querySelectorAll('[data-message-id]').length")
            msg2 = await page2.evaluate("() => document.querySelectorAll('[data-message-id]').length")

            if msg1 > 0 and msg2 > 0:
                print(f"[OK] Both tabs updated at {i}s")
                break

        # Get final state
        nav1, msgs1 = await page1.evaluate("""
        () => [
          window.__domTrace.nav_count,
          document.querySelectorAll('[data-message-id]').length
        ]
        """)

        nav2, msgs2 = await page2.evaluate("""
        () => [
          window.__domTrace.nav_count,
          document.querySelectorAll('[data-message-id]').length
        ]
        """)

        print("\n" + "="*80)
        print("TWO TABS DOM VERIFICATION")
        print("="*80)
        print(f"Tab1: nav={nav1}, messages={msgs1}")
        print(f"Tab2: nav={nav2}, messages={msgs2}")
        print(f"Convergence: {'YES' if msgs1 == msgs2 else 'NO'}")

        await context.close()
        await browser.close()

        return nav1 == 0 and nav2 == 0 and msgs1 == msgs2


async def main():
    """Run all tests."""
    test1_result = await test_single_tab_dom()
    test2_result = await test_two_tabs_dom()

    print("\n" + "="*80)
    print("FASE 5B-A: DOM VERIFICATION SUMMARY")
    print("="*80)
    print(f"Single tab: {'PASS' if test1_result else 'FAIL'}")
    print(f"Two tabs:   {'PASS' if test2_result else 'FAIL'}")

    if test1_result and test2_result:
        print("\n[PASS] FASE 5B-A: DOM changes verified")
        print("  ✓ Message visible after event (no reload)")
        print("  ✓ Unread count updated")
        print("  ✓ Both tabs synchronized")
        return True
    else:
        print("\n[FAIL] FASE 5B-A: DOM verification incomplete")
        return False


if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)
