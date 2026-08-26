"""FASE 5B: Real browser SSE test with automatic event publishing."""
import asyncio
import json
import subprocess
import os
import time
from datetime import datetime
from playwright.async_api import async_playwright


async def publish_test_event():
    """Publish test event via Django management command."""
    correlation_id = f"sse-test-{int(time.time()*1000)}"
    try:
        result = subprocess.run(
            [
                'docker', 'exec', 'taxicarga-api',
                'python', '-c',
                f'''
import os
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_e2e"
import django
django.setup()
from apps.whatsapp.redis_events import get_event_bus
bus = get_event_bus()
event = bus.publish(
    "message.created",
    {{"conversation_id": 2, "channel_id": 2, "cliente_id": 3, "message_id": 9999,
      "meta_message_id": "{correlation_id}", "sender_type": "test", "direction": "test",
      "preview": "SSE Browser Test Event", "timestamp": {time.time()}, "correlation_id": "{correlation_id}"}}
)
print(f"PUBLISHED:{{event.id}}")
'''
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        for line in (result.stdout + result.stderr).split('\n'):
            if line.startswith('PUBLISHED:'):
                event_id = line.split(':')[1]
                return {'correlation_id': correlation_id, 'event_id': event_id}

        print(f"Warning: publish failed to return event ID. stdout={result.stdout[:100]}")
        return None
    except Exception as e:
        print(f"[ERROR] Publish failed: {str(e)[:100]}")
        return None


async def run_sse_browser_test():
    """Test EventSource with real browser."""
    print("\n" + "="*80)
    print("FASE 5B — SSE BROWSER TEST")
    print("="*80)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # State tracking
        state = {
            'sse_connected': False,
            'heartbeats': [],
            'events_received': [],
            'errors': [],
            'console_logs': [],
        }

        def on_console(msg):
            """Capture browser console messages."""
            log_entry = {'type': msg.type, 'text': msg.text, 'time': datetime.now().isoformat()}
            state['console_logs'].append(log_entry)
            print(f"[CONSOLE {msg.type}] {msg.text[:100]}")

        def on_response(response):
            """Track network responses."""
            if 'events/stream' in response.url:
                print(f"[NETWORK] SSE endpoint: {response.status}")

        page.on('console', on_console)
        page.on('response', on_response)

        try:
            # Step 1: Navigate to dashboard
            print("\n[STEP 1] Navigate to dashboard")
            print("-" * 80)
            await page.goto('http://localhost:8001/login', wait_until='domcontentloaded')
            print("[OK] Navigated to login")

            # Step 2: Check if login form is present
            print("\n[STEP 2] Check login page")
            print("-" * 80)
            try:
                await page.wait_for_selector('input[name="username"]', timeout=5000)
                print("✓ Login form found")

                # Try to find username field and fill it
                username_input = await page.query_selector('input[name="username"]')
                if username_input:
                    await username_input.fill('admin')
                    print("✓ Filled username")

                password_input = await page.query_selector('input[name="password"]')
                if password_input:
                    await password_input.fill('admin')
                    print("✓ Filled password")

                submit_btn = await page.query_selector('button[type="submit"]')
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    print("✓ Login submitted")
                else:
                    print("✗ Submit button not found")

            except Exception as e:
                print(f"⚠ Login form interaction failed: {str(e)[:80]}")

            # Step 3: Wait for dashboard to load
            print("\n[STEP 3] Wait for dashboard")
            print("-" * 80)
            await asyncio.sleep(2)
            await page.screenshot(path='/tmp/sse_test_step3.png')
            print("✓ Screenshot taken")

            # Step 4: Inject EventSource listener script
            print("\n[STEP 4] Inject EventSource listener")
            print("-" * 80)

            listener_script = '''
            (function() {
                window.__sse_test__ = {
                    connected: false,
                    heartbeats: [],
                    events: [],
                    errors: []
                };

                const url = '/dashboard/whatsapp/api/events/stream/';
                console.log('[SSE TEST] Opening connection to: ' + url);

                const eventSource = new EventSource(url, { withCredentials: true });

                eventSource.addEventListener('open', function(e) {
                    window.__sse_test__.connected = true;
                    console.log('[SSE OPEN] Connection established. readyState=' + e.target.readyState);
                });

                eventSource.addEventListener('message', function(e) {
                    const data = JSON.parse(e.data);
                    window.__sse_test__.events.push({
                        id: e.lastEventId,
                        data: data,
                        timestamp: new Date().toISOString()
                    });
                    console.log('[SSE MESSAGE] Received: ' + e.lastEventId + ' type=' + e.type);
                });

                // Listen for named events
                eventSource.addEventListener('message.created', function(e) {
                    const data = JSON.parse(e.data);
                    window.__sse_test__.events.push({
                        id: e.lastEventId,
                        type: 'message.created',
                        data: data,
                        timestamp: new Date().toISOString()
                    });
                    console.log('[SSE message.created] Received: correlation_id=' + (data.correlation_id || 'N/A'));
                });

                eventSource.addEventListener('error', function(e) {
                    window.__sse_test__.errors.push({
                        readyState: e.target.readyState,
                        timestamp: new Date().toISOString()
                    });
                    console.log('[SSE ERROR] Connection error. readyState=' + e.target.readyState);
                });

                // Track heartbeats
                eventSource.addEventListener('heartbeat', function(e) {
                    window.__sse_test__.heartbeats.push({
                        data: e.data,
                        timestamp: new Date().toISOString()
                    });
                    console.log('[SSE HEARTBEAT] ' + e.data);
                });

                // Track comments (heartbeats from ): comment events
                const origAddEventListener = eventSource.addEventListener.bind(eventSource);
                eventSource.addEventListener = function(event, handler, useCapture) {
                    if (event === '*' || event === 'heartbeat') {
                        origAddEventListener(event, handler, useCapture);
                    }
                    origAddEventListener(event, handler, useCapture);
                };

                console.log('[SSE TEST] EventSource listener attached');
                window.__sse_test__.eventSource = eventSource;
            })();
            '''

            await page.evaluate(listener_script)
            print("✓ EventSource listener injected")

            # Step 5: Wait for SSE to connect
            print("\n[STEP 5] Wait for SSE connection")
            print("-" * 80)
            await asyncio.sleep(2)

            connected = await page.evaluate('() => window.__sse_test__.connected')
            print(f"SSE connected: {connected}")

            if not connected:
                print("⚠ SSE not connected yet, waiting...")
                for i in range(10):
                    await asyncio.sleep(0.5)
                    connected = await page.evaluate('() => window.__sse_test__.connected')
                    if connected:
                        print(f"✓ SSE connected after {(i+1)*0.5}s")
                        break

            if not connected:
                print("✗ SSE connection failed")

            # Step 6: Publish test event
            print("\n[STEP 6] Publish test event")
            print("-" * 80)
            event_data = await publish_test_event()

            if event_data:
                print(f"✓ Event published: {event_data['event_id']}")
                print(f"  Correlation ID: {event_data['correlation_id']}")
            else:
                print("✗ Event publish failed")
                event_data = {}

            # Step 7: Wait for event to arrive
            print("\n[STEP 7] Wait for event to arrive")
            print("-" * 80)
            correlation_id = event_data.get('correlation_id', '')

            for i in range(20):  # Wait up to 10 seconds
                await asyncio.sleep(0.5)
                events = await page.evaluate('() => window.__sse_test__.events')
                heartbeats = await page.evaluate('() => window.__sse_test__.heartbeats')

                print(f"  [{i}] Events: {len(events)}, Heartbeats: {len(heartbeats)}")

                # Check if test event arrived
                for evt in events:
                    if evt.get('data', {}).get('correlation_id') == correlation_id:
                        print(f"✓ TEST EVENT RECEIVED! ID={evt['id']}")
                        await page.screenshot(path='/tmp/sse_test_step7_success.png')
                        break

            # Step 8: Final state report
            print("\n[STEP 8] Final state report")
            print("-" * 80)

            events = await page.evaluate('() => window.__sse_test__.events')
            heartbeats = await page.evaluate('() => window.__sse_test__.heartbeats')
            errors = await page.evaluate('() => window.__sse_test__.errors')
            connected = await page.evaluate('() => window.__sse_test__.connected')

            print(f"SSE connected: {connected}")
            print(f"Events received: {len(events)}")
            print(f"Heartbeats received: {len(heartbeats)}")
            print(f"Errors: {len(errors)}")

            if events:
                print("\nEvents:")
                for evt in events[-3:]:  # Last 3 events
                    print(f"  - {evt['id']}: {evt.get('type', 'N/A')} ({evt.get('data', {}).get('preview', 'N/A')[:40]})")

            test_event_found = any(
                evt.get('data', {}).get('correlation_id') == correlation_id
                for evt in events
            )

            if test_event_found:
                print("\n✓✓✓ SUCCESS: Test event received by browser")
            else:
                print("\n✗✗✗ FAILURE: Test event NOT received by browser")

            await page.screenshot(path='/tmp/sse_test_final.png')

        except Exception as e:
            print(f"\n✗ Exception: {type(e).__name__}: {str(e)[:100]}")
            import traceback
            traceback.print_exc()

        finally:
            await context.close()
            await browser.close()

        print("\n" + "="*80)
        print("TEST COMPLETE")
        print("="*80 + "\n")


if __name__ == '__main__':
    asyncio.run(run_sse_browser_test())
