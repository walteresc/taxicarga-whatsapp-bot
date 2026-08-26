"""FASE 5B: Full auth -> SSE test with Playwright."""
import asyncio
import subprocess
import time
from playwright.async_api import async_playwright


async def setup_test_user():
    """Create/verify test user with WhatsApp permissions."""
    print("\n[SETUP] Verify test user in Django")
    print("-" * 80)

    cmd = [
        'docker', 'exec', 'taxicarga-api',
        'python', 'manage.py', 'shell', '-c',
        '''
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_e2e")
import django
django.setup()

from django.contrib.auth.models import User, Group

# Create/verify test user
user, created = User.objects.get_or_create(
    username='e2e_test',
    defaults={'email': 'e2e@test.local', 'is_staff': True, 'is_superuser': True}
)

if created:
    user.set_password('e2e_test')
    user.save()
    print("CREATED")
else:
    print("EXISTS")

print(f"USER:e2e_test:is_superuser={user.is_superuser}:is_staff={user.is_staff}")
'''
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    for line in result.stdout.split('\n'):
        if 'USER:' in line or 'CREATED' in line or 'EXISTS' in line:
            print(f"[OK] {line}")


async def test_sse_full_flow():
    """Full auth + SSE test."""
    print("\n" + "="*80)
    print("FASE 5B - FULL AUTH + SSE TEST")
    print("="*80)

    # Setup
    await setup_test_user()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        console_logs = []
        def on_console(msg):
            text = str(msg.text)[:80]
            console_logs.append(text)
            print(f"[CONSOLE] {text}")

        page.on('console', on_console)

        try:
            # Step 1: Navigate to login
            print("\n[STEP 1] Navigate to login")
            print("-" * 80)
            response = await page.goto(
                'http://localhost:8001/dashboard/login/',
                wait_until='domcontentloaded'
            )
            print(f"[OK] Status: {response.status}")

            # Step 2: Fill and submit login form
            print("\n[STEP 2] Login with test user")
            print("-" * 80)

            try:
                # Wait for Vue to mount (check for the login card)
                await page.wait_for_selector('form', timeout=10000)
                print("[OK] Login form loaded")

                # Fill inputs using JavaScript (more reliable with Vue/Vuetify)
                await page.evaluate('''
                () => {
                    const username = document.querySelector('input[name="username"]');
                    const password = document.querySelector('input[name="password"]');
                    if (username) {
                        username.value = 'e2e_test';
                        username.dispatchEvent(new Event('input', { bubbles: true }));
                        username.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    if (password) {
                        password.value = 'e2e_test';
                        password.dispatchEvent(new Event('input', { bubbles: true }));
                        password.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
                ''')
                print("[OK] Filled credentials")

                # Click submit button
                submit_btn = await page.query_selector('button[type="submit"]')
                if submit_btn:
                    await submit_btn.click()
                    # Wait for redirect after login
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    print("[OK] Login submitted and redirected")
                else:
                    print("[FAIL] Could not find submit button")
                    return

            except Exception as e:
                print(f"[FAIL] Login error: {str(e)[:60]}")
                import traceback
                traceback.print_exc()
                return

            # Step 3: Verify session
            print("\n[STEP 3] Verify session")
            print("-" * 80)

            cookies = await context.cookies()
            sessionid = None
            for cookie in cookies:
                if cookie['name'] == 'sessionid':
                    sessionid = cookie['value']
                    print(f"[OK] Found sessionid: {cookie['value'][:20]}...")
                    break

            if not sessionid:
                print("[FAIL] No sessionid cookie found")
                return

            # Step 4: Test SSE endpoint (should return 200 + event-stream)
            print("\n[STEP 4] Test SSE endpoint response")
            print("-" * 80)

            # Using fetch with credentials to include cookies
            response_check = await page.evaluate('''
            async () => {
                const resp = await fetch('/dashboard/whatsapp/api/events/stream/', {
                    credentials: 'include'
                });
                return {
                    status: resp.status,
                    contentType: resp.headers.get('content-type'),
                    url: resp.url
                };
            }
            ''')

            print(f"[OK] Status: {response_check['status']}")
            print(f"[OK] Content-Type: {response_check['contentType']}")

            if response_check['status'] == 401:
                print("[FAIL] Still receiving 401 (authentication failed)")
                return
            elif response_check['status'] == 403:
                print("[FAIL] Receiving 403 (authorization failed)")
                return
            elif response_check['status'] == 200:
                if 'event-stream' in response_check['contentType']:
                    print("[OK] Correct Content-Type: text/event-stream")
                else:
                    print(f"[FAIL] Wrong Content-Type: {response_check['contentType']}")
                    return
            else:
                print(f"[FAIL] Unexpected status: {response_check['status']}")
                return

            # Step 5: Initialize EventSource
            print("\n[STEP 5] Initialize EventSource")
            print("-" * 80)

            listener_js = """
            window.sse_state = {
                events: [],
                connected: false,
                errors: [],
                heartbeats: 0
            };

            const es = new EventSource('/dashboard/whatsapp/api/events/stream/', {
                withCredentials: true
            });

            es.addEventListener('open', () => {
                window.sse_state.connected = true;
                console.log('[SSE OPEN] Connected');
            });

            es.addEventListener('message', (e) => {
                window.sse_state.events.push({
                    id: e.lastEventId,
                    type: e.type,
                    data: e.data
                });
                console.log('[SSE MSG] ' + e.lastEventId);
            });

            es.addEventListener('error', (e) => {
                window.sse_state.errors.push(e.target.readyState);
                console.log('[SSE ERROR] readyState=' + e.target.readyState);
            });

            window.sse_state.eventSource = es;
            console.log('[SSE INIT] EventSource created');
            """

            await page.evaluate(listener_js)
            print("[OK] Listener initialized")

            # Step 6: Wait for connection
            print("\n[STEP 6] Wait for SSE connection (5s)")
            print("-" * 80)

            for i in range(10):
                connected = await page.evaluate('() => window.sse_state.connected')
                errors = await page.evaluate('() => window.sse_state.errors')

                if connected:
                    print(f"[OK] Connected after {i}s")
                    break

                if errors and errors[-1] == 2:
                    print(f"[FAIL] Connection error (readyState=2 means closed)")
                    break

                await asyncio.sleep(0.5)
            else:
                print("[WARN] Connection timeout, but continuing...")

            # Step 7: Publish test event
            print("\n[STEP 7] Publish test event")
            print("-" * 80)

            cmd_publish = [
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
        "meta_message_id": "AUTH_TEST_{int(time.time()*1000)}",
        "sender_type": "test",
        "direction": "test",
        "preview": "AUTH Test Event",
        "timestamp": time.time()
    }}
)
print(f"EVENT:{{event.id}}")
'''
            ]

            result = subprocess.run(cmd_publish, capture_output=True, text=True, timeout=10)
            event_id = None
            for line in result.stdout.split('\n'):
                if 'EVENT:' in line:
                    event_id = line.split(':')[1]
                    print(f"[OK] Published: {event_id}")
                    break

            # Step 8: Wait for event
            print("\n[STEP 8] Wait for event (10s)")
            print("-" * 80)

            for i in range(20):
                events = await page.evaluate('() => window.sse_state.events')
                print(f"   [{i}] Events: {len(events)}")

                if len(events) > 0:
                    print(f"[SUCCESS] Received {len(events)} events!")
                    for evt in events[-1:]:
                        print(f"   Event ID: {evt['id']}")
                        print(f"   Data: {evt['data'][:60]}")
                    break

                await asyncio.sleep(0.5)

            # Final summary
            print("\n[SUMMARY]")
            print("-" * 80)

            connected = await page.evaluate('() => window.sse_state.connected')
            events = await page.evaluate('() => window.sse_state.events')
            errors = await page.evaluate('() => window.sse_state.errors')

            print(f"Connected: {connected}")
            print(f"Events received: {len(events)}")
            print(f"Errors: {len(errors)}")

            if connected and len(events) > 0:
                print("\n[PASS] FULL AUTH -> SSE -> EVENTS WORKING")
            else:
                print("\n[FAIL] Issue detected")

        except Exception as e:
            print(f"\n[EXCEPTION] {type(e).__name__}: {str(e)[:100]}")

        finally:
            await context.close()
            await browser.close()

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80 + "\n")


if __name__ == '__main__':
    asyncio.run(test_sse_full_flow())
