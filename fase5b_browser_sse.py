"""FASE 5B: Real browser SSE test - ASCII version."""
import asyncio
import subprocess
import time
from datetime import datetime
from playwright.async_api import async_playwright


async def publish_test_event():
    """Publish test event via Django."""
    correlation_id = f"browser-test-{int(time.time()*1000)}"
    try:
        cmd = [
            'docker', 'exec', 'taxicarga-api',
            'python', 'manage.py', 'fase5b_sse_e2e'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        # Extract event ID from output
        for line in result.stdout.split('\n'):
            if 'Published event:' in line:
                parts = line.split('Published event:')
                if len(parts) > 1:
                    event_id = parts[1].strip().split()[0]
                    return {'correlation_id': correlation_id, 'event_id': event_id}

        return None
    except Exception as e:
        print(f"[ERROR] Publish failed: {str(e)[:100]}")
        return None


async def main():
    """Main test."""
    print("\n" + "="*80)
    print("FASE 5B - SSE BROWSER TEST")
    print("="*80)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        state = {
            'sse_open': False,
            'events': [],
            'errors': [],
        }

        def on_console(msg):
            text = str(msg.text)[:80]
            print(f"[CONSOLE] {text}")
            if 'SSE' in text:
                state['events'].append(text)

        page.on('console', on_console)

        try:
            # Navigate
            print("\n[STEP 1] Navigate to localhost:8001")
            print("-" * 80)
            response = await page.goto('http://localhost:8001/', timeout=10000)
            print(f"[OK] Status: {response.status}")

            # Wait for page to load
            await asyncio.sleep(2)

            # Inject SSE listener
            print("\n[STEP 2] Inject EventSource listener")
            print("-" * 80)

            listener_js = """
            window.sse_state = { events: [], connected: false };
            const es = new EventSource('/dashboard/whatsapp/api/events/stream/', { withCredentials: true });

            es.onopen = () => {
                window.sse_state.connected = true;
                console.log('[SSE] Connected');
            };

            es.onmessage = (e) => {
                window.sse_state.events.push(e.data);
                console.log('[SSE] Message: ' + e.lastEventId);
            };

            es.onerror = (e) => {
                console.log('[SSE] Error: readyState=' + e.target.readyState);
            };

            // Heartbeats (comment lines starting with :)
            // These come through but don't trigger message events
            console.log('[SSE] Listener attached');
            """

            await page.evaluate(listener_js)
            print("[OK] Listener injected")

            # Wait for connection
            print("\n[STEP 3] Wait for SSE connection")
            print("-" * 80)
            for i in range(10):
                connected = await page.evaluate('() => window.sse_state.connected')
                if connected:
                    print(f"[OK] Connected after {i}s")
                    break
                await asyncio.sleep(1)

            # Publish event
            print("\n[STEP 4] Publish test event")
            print("-" * 80)
            event_info = await publish_test_event()
            if event_info:
                print(f"[OK] Published: {event_info['event_id']}")
            else:
                print("[FAIL] Publish failed")

            # Wait for event
            print("\n[STEP 5] Wait for event (10s)")
            print("-" * 80)
            for i in range(20):
                await asyncio.sleep(0.5)
                count = await page.evaluate('() => window.sse_state.events.length')
                if count > 0:
                    print(f"[OK] Received {count} events")
                    events = await page.evaluate('() => window.sse_state.events')
                    for evt in events[-1:]:
                        print(f"   Event: {str(evt)[:100]}")
                    break
                else:
                    if i % 4 == 0:
                        print(f"   [{i}] Waiting...")

            # Final check
            final_count = await page.evaluate('() => window.sse_state.events.length')
            print(f"\n[RESULT] Total events: {final_count}")

            if final_count > 0:
                print("[SUCCESS] SSE received events from browser")
            else:
                print("[FAIL] SSE received NO events")

        except Exception as e:
            print(f"\n[EXCEPTION] {type(e).__name__}: {str(e)[:100]}")

        finally:
            await context.close()
            await browser.close()

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80 + "\n")


if __name__ == '__main__':
    asyncio.run(main())
