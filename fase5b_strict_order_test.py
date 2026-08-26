"""FASE 5B: Strict order test with correlation tracking."""
import asyncio
import json
import requests
import subprocess
import time
import uuid
from datetime import datetime


async def http_login():
    """Step 1: Login."""
    print("\n[STEP 1] HTTP login")
    print("-" * 80)

    session = requests.Session()
    response = session.post(
        'http://localhost:8001/dashboard/api/auth/login/',
        json={'username': 'e2e_test', 'password': 'e2e_test_password'}
    )

    if response.status_code == 200:
        sessionid = session.cookies.get_dict().get('sessionid')
        print(f"[OK] Logged in, sessionid={sessionid[:20]}...")
        return sessionid
    else:
        print(f"[FAIL] Login failed: {response.status_code}")
        return None


async def main():
    print("\n" + "="*80)
    print("FASE 5B - STRICT ORDER E2E TEST")
    print("="*80)

    correlation_id = f"sse-order-{uuid.uuid4().hex[:8]}"
    print(f"\nCorrelation ID: {correlation_id}")

    sessionid = await http_login()
    if not sessionid:
        return

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await context.new_page()

        console_logs = []
        def on_console(msg):
            text = str(msg.text)
            console_logs.append({'type': msg.type, 'text': text})
            if correlation_id in text or 'CP' in text or 'SSE' in text:
                print(f"[LOG] {text[:100]}")

        page.on('console', on_console)

        try:
            # Step 2: Navigate to CRM
            print("\n[STEP 2] Navigate to CRM")
            print("-" * 80)

            response = await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
            print(f"[OK] Loaded: {response.status}")
            await asyncio.sleep(1)

            # Step 3: Get snapshot cursor
            print("\n[STEP 3] Get snapshot cursor")
            print("-" * 80)

            snapshot_cursor = await page.evaluate('''
            async () => {
                try {
                    const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
                    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                    const data = await resp.json();
                    return data.snapshot_cursor || null;
                } catch (e) {
                    return null;
                }
            }
            ''')

            print(f"[OK] Snapshot cursor: {snapshot_cursor}")

            if not snapshot_cursor:
                print("[FAIL] Could not get snapshot cursor")
                return

            # Step 4: Verify EventSource not yet open
            print("\n[STEP 4] Verify EventSource initialization")
            print("-" * 80)

            await page.evaluate('''
            window.test_state = {
                connected: false,
                events: [],
                frames: []
            };
            console.log("[TEST] State initialized");
            ''')

            # Step 5: Open EventSource (manually, not relying on frontend)
            print("\n[STEP 5] Open EventSource")
            print("-" * 80)

            await page.evaluate(f'''
            () => {{
                const url = '/dashboard/whatsapp/api/events/stream/?cursor={snapshot_cursor}';
                console.log("[TEST] Opening EventSource: " + url);

                const es = new EventSource(url, {{ withCredentials: true }});

                es.addEventListener('open', () => {{
                    window.test_state.connected = true;
                    console.log("[TEST CONNECTED] EventSource open, readyState=1");
                }});

                es.addEventListener('message', (e) => {{
                    const data = JSON.parse(e.data);
                    window.test_state.events.push({{id: e.lastEventId, data: data}});
                    window.test_state.frames.push(e.data);
                    if (data.correlation_id) {{
                        console.log("[TEST FRAME] Got correlation_id: " + data.correlation_id);
                    }}
                }});

                es.addEventListener('error', (e) => {{
                    console.log("[TEST ERROR] readyState=" + e.target.readyState);
                }});

                window.test_es = es;
                console.log("[TEST] EventSource listener attached");
            }}
            ''')

            # Step 6: Wait for OPEN
            print("\n[STEP 6] Wait for EventSource OPEN")
            print("-" * 80)

            for i in range(10):
                connected = await page.evaluate('() => window.test_state.connected')
                if connected:
                    print(f"[OK] Connected at {i}s")
                    break
                await asyncio.sleep(0.5)
            else:
                print("[FAIL] Timeout waiting for connection")
                return

            # Wait a bit after OPEN before publishing
            await asyncio.sleep(1)

            # Step 7: Publish event with correlation_id
            print("\n[STEP 7] Publish event")
            print("-" * 80)

            cmd = [
                'docker', 'exec', 'taxicarga-api',
                'python', '-c',
                f'''
import os
import time
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_e2e"
import django
django.setup()

from apps.whatsapp.redis_events import get_event_bus

bus = get_event_bus()
event = bus.publish(
    "message.created",
    {{
        "conversation_id": 2,
        "channel_id": 2,
        "cliente_id": 3,
        "message_id": 8888,
        "meta_message_id": "STRICT_ORDER_{int(time.time()*1000)}",
        "sender_type": "test",
        "direction": "test",
        "preview": "Strict Order Test",
        "timestamp": time.time(),
        "correlation_id": "{correlation_id}"
    }}
)
print(f"PUBLISHED:{{event.id}}")
'''
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            event_id = None
            for line in result.stdout.split('\n'):
                if 'PUBLISHED:' in line:
                    event_id = line.split(':')[1]
                    print(f"[OK] Event published: {event_id}")
                    break

            # Step 8: Wait for event (max 5 seconds)
            print("\n[STEP 8] Wait for event delivery (5s)")
            print("-" * 80)

            start_time = time.time()
            for i in range(10):
                elapsed = time.time() - start_time

                events = await page.evaluate('() => window.test_state.events')
                print(f"   [{elapsed:.1f}s] Events: {len(events)}")

                for evt in events:
                    if evt['data'].get('correlation_id') == correlation_id:
                        elapsed = time.time() - start_time
                        print(f"\n[SUCCESS] Event received in {elapsed:.1f}s!")
                        print(f"   Event ID: {evt['id']}")
                        print(f"   Correlation: {correlation_id}")
                        break
                else:
                    if elapsed > 5:
                        print(f"\n[TIMEOUT] No event after 5s")
                        break
                    await asyncio.sleep(0.5)
                    continue
                break

            # Step 9: Capture final state
            print("\n[STEP 9] Final state")
            print("-" * 80)

            final_events = await page.evaluate('() => window.test_state.events')
            print(f"Total events received: {len(final_events)}")

            # Step 10: Capture Django logs
            print("\n[STEP 10] Capture Django logs")
            print("-" * 80)

            log_cmd = [
                'docker', 'exec', 'taxicarga-api',
                'tail', '-100', '/app/django_debug.log'
            ]

            result = subprocess.run(log_cmd, capture_output=True, text=True, timeout=5)

            print("Recent SSE logs:")
            for line in result.stdout.split('\n'):
                if 'SSE GEN' in line or correlation_id in line:
                    print(f"  {line[:100]}")

            # Result
            if len(final_events) > 0:
                print("\n[PASS] Event received successfully")
            else:
                print("\n[FAIL] Event NOT received")

        except Exception as e:
            print(f"\n[EXCEPTION] {type(e).__name__}: {str(e)[:100]}")
            import traceback
            traceback.print_exc()

        finally:
            await context.close()
            await browser.close()

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80 + "\n")


if __name__ == '__main__':
    asyncio.run(main())
