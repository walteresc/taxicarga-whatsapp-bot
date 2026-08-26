"""FASE 5B: HTTP login + SSE test (simpler, more reliable)."""
import asyncio
import json
import requests
import time
from playwright.async_api import async_playwright


async def http_login():
    """Login via API endpoint to get session cookie."""
    print("\n[LOGIN] HTTP POST to /dashboard/api/auth/login/")
    print("-" * 80)

    session = requests.Session()

    # POST to API login endpoint
    login_data = {
        'username': 'e2e_test',
        'password': 'e2e_test_password',
    }

    response = session.post(
        'http://localhost:8001/dashboard/api/auth/login/',
        json=login_data
    )

    print(f"[OK] Login response: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"[OK] Login successful: {result.get('status')}")

        # Get session cookie
        cookies = session.cookies.get_dict()
        sessionid = cookies.get('sessionid')
        if sessionid:
            print(f"[OK] Got sessionid: {sessionid[:20]}...")
            return sessionid
        else:
            print("[FAIL] No sessionid in cookies")
            print(f"Cookies: {cookies}")
            return None
    else:
        print(f"[FAIL] Login failed with {response.status_code}")
        if response.text:
            print(f"Response: {response.text[:100]}")
        return None


async def test_sse_with_auth():
    """Test SSE with authenticated session."""
    print("\n" + "="*80)
    print("FASE 5B - HTTP AUTH + SSE TEST")
    print("="*80)

    # HTTP login
    sessionid = await http_login()
    if not sessionid:
        print("\n[ABORT] Could not authenticate via HTTP")
        return

    # Use authenticated session with Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            extra_http_headers={
                'Cookie': f'sessionid={sessionid}'
            }
        )
        page = await context.new_page()

        console_logs = []
        def on_console(msg):
            text = str(msg.text)[:80]
            console_logs.append(text)
            print(f"[CONSOLE] {text}")

        page.on('console', on_console)

        try:
            # Step 1: Navigate to dashboard
            print("\n[STEP 1] Navigate to dashboard")
            print("-" * 80)

            response = await page.goto(
                'http://localhost:8001/dashboard/',
                wait_until='domcontentloaded'
            )
            print(f"[OK] Status: {response.status}")

            await asyncio.sleep(1)

            # Step 2: Test SSE endpoint directly
            print("\n[STEP 2] Test SSE endpoint")
            print("-" * 80)

            sse_check = await page.evaluate('''
            async () => {
                const resp = await fetch('/dashboard/whatsapp/api/events/stream/', {
                    credentials: 'include'
                });
                return {
                    status: resp.status,
                    contentType: resp.headers.get('content-type'),
                };
            }
            ''')

            print(f"[OK] Status: {sse_check['status']}")
            print(f"[OK] Content-Type: {sse_check['contentType']}")

            if sse_check['status'] != 200:
                print(f"[FAIL] Expected 200, got {sse_check['status']}")
                return

            if 'event-stream' not in sse_check['contentType']:
                print(f"[FAIL] Wrong Content-Type: {sse_check['contentType']}")
                return

            # Step 3: Initialize EventSource
            print("\n[STEP 3] Initialize EventSource")
            print("-" * 80)

            await page.evaluate('''
            window.sse_test = {
                events: [],
                connected: false
            };

            const es = new EventSource('/dashboard/whatsapp/api/events/stream/', {
                withCredentials: true
            });

            es.onopen = () => {
                window.sse_test.connected = true;
                console.log('[SSE] Connected');
            };

            es.onmessage = (e) => {
                window.sse_test.events.push(e.data);
                console.log('[SSE] Got event: ' + e.lastEventId);
            };

            es.onerror = (e) => {
                console.log('[SSE] Error: readyState=' + e.target.readyState);
            };

            console.log('[SSE] Listener attached');
            ''')

            print("[OK] Listener attached")

            # Step 4: Wait for connection
            print("\n[STEP 4] Wait for SSE connection")
            print("-" * 80)

            for i in range(10):
                connected = await page.evaluate('() => window.sse_test.connected')
                if connected:
                    print(f"[OK] Connected")
                    break
                await asyncio.sleep(0.5)
            else:
                print("[WARN] Connection timeout")

            # Step 5: Publish event
            print("\n[STEP 5] Publish test event")
            print("-" * 80)

            import subprocess
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
        "message_id": 9999,
        "meta_message_id": "HTTP_AUTH_{int(time.time()*1000)}",
        "sender_type": "test",
        "preview": "HTTP Auth Test"
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

            # Step 6: Wait for event
            print("\n[STEP 6] Wait for event (10s)")
            print("-" * 80)

            for i in range(20):
                events = await page.evaluate('() => window.sse_test.events')
                if i % 4 == 0:
                    print(f"   [{i}] Events: {len(events)}")

                if len(events) > 0:
                    print(f"[SUCCESS] Received {len(events)} events!")
                    for evt_json in events[-1:]:
                        evt = json.loads(evt_json)
                        print(f"   Data: {str(evt)[:80]}")
                    break

                await asyncio.sleep(0.5)

            # Final report
            print("\n[SUMMARY]")
            print("-" * 80)

            connected = await page.evaluate('() => window.sse_test.connected')
            events = await page.evaluate('() => window.sse_test.events')

            print(f"Connected: {connected}")
            print(f"Events received: {len(events)}")

            if connected and len(events) > 0:
                print("\n[PASS] HTTP AUTH -> SSE -> EVENTS WORKING")
            else:
                print("\n[FAIL] Issue detected")

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
    asyncio.run(test_sse_with_auth())
