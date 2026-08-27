"""
FASE 5B E2E Validation: SSE real-time message replay
Strict order: Browser -> Login -> SSE OPEN -> Replay -> DOM update (no F5)
"""
import asyncio
import json
import subprocess
import os
from datetime import datetime
from playwright.async_api import async_playwright


async def replay_test005():
    """Execute TEST-005 replay via Docker management command."""
    try:
        # Call Django management command via docker-compose exec
        result = subprocess.run(
            ['docker-compose', 'exec', '-T', 'django', 'python', 'manage.py', 'replay_test005'],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=10
        )

        # Parse output to extract event_id
        # Looking for: "✓ Replay published: event_id=1787674950920-0, msg_id=117"
        if 'event_id=' in result.stdout or 'event_id=' in result.stderr:
            combined = result.stdout + result.stderr
            for line in combined.split('\n'):
                if 'event_id=' in line:
                    # Extract pattern: event_id=1787674950920-0
                    import re
                    match = re.search(r'event_id=([0-9-]+)', line)
                    if match:
                        return match.group(1)
        return None
    except Exception as e:
        print(f"[ERROR] Replay failed: {str(e)[:100]}")
        return None


async def run_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # State tracking
        state = {
            'console': [],
            'network': [],
            'sse_open': False,
            'test005_found': False,
            'screenshot': None,
        }

        def on_console(msg):
            state['console'].append({
                'type': msg.type,
                'text': msg.text,
                'time': datetime.now().isoformat(),
            })
            # Track CP10 (SSE OPEN)
            if '[REALTIME CP10]' in msg.text or 'readyState=1' in msg.text:
                state['sse_open'] = True
                print(f"[OK] [EVENT] SSE OPEN detected at {datetime.now().isoformat()}")
            # Track TEST-005 in DOM
            if 'TEST-005' in msg.text or 'FRONTEND-TEST' in msg.text:
                print(f"     [EVENT] TEST-005 reference: {msg.text[:80]}")

        def on_response(response):
            state['network'].append({
                'url': response.url,
                'status': response.status,
                'headers': dict(response.headers),
                'time': datetime.now().isoformat(),
            })
            # Track SSE connection
            if 'events/stream' in response.url:
                print(f"  [NETWORK] SSE endpoint: {response.status} {response.headers.get('content-type', 'unknown')}")

        page.on('console', on_console)
        page.on('response', on_response)

        print("\n" + "="*80)
        print("FASE 5B E2E: TEST-005 Real-time Replay")
        print("="*80 + "\n")

        # STEP 1: Navigate to login
        print("[STEP 1] Navigating to login...")
        await page.goto('http://localhost:8001/login', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(3)  # Wait longer for Vue/Vuetify to mount

        # STEP 2: Submit login via form POST
        print("[STEP 2] Submitting login form...")
        await asyncio.sleep(2)

        # Use direct form submission instead of Vuetify components
        try:
            # Get the form element
            form = await page.query_selector('form')
            if not form:
                print("[WARN] [STEP 2] Form not found, skipping login...")
            else:
                # Use page.goto with POST via form data
                # We'll use direct API call instead
                await page.evaluate('''
                    async () => {
                        const form = document.querySelector('form');
                        const csrfToken = document.querySelector('[name="csrfmiddlewaretoken"]')?.value;
                        const data = new FormData();
                        data.append('username', 'demo_vendedor');
                        data.append('password', 'demo_vendedor');
                        if (csrfToken) data.append('csrfmiddlewaretoken', csrfToken);

                        console.log('[TEST] Submitting form with fetch...');
                        const res = await fetch(form.action, {
                            method: 'POST',
                            body: data,
                            credentials: 'include'
                        });
                        console.log('[TEST] Form response:', res.status);
                    }
                ''')

                # Wait a bit for the request to process
                await asyncio.sleep(2)

                # Navigate to dashboard to confirm login
                try:
                    await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded', timeout=10000)
                    print("[OK] [STEP 2] Login processed, navigated to dashboard")
                except:
                    print("[WARN] [STEP 2] Dashboard navigation unclear")
        except Exception as e:
            print(f"[WARN] [STEP 2] Login error: {str(e)[:100]}")

        # STEP 3: Navigate to bandeja
        print("[STEP 3] Navigating to bandeja-entrada...")
        await page.goto('http://localhost:8001/atencion/bandeja-entrada/', wait_until='networkidle', timeout=15000)

        # STEP 4: Wait for SSE OPEN
        print("[STEP 4] Waiting for SSE OPEN (CP10)...")
        for i in range(60):  # Wait up to 60 seconds
            if state['sse_open']:
                break
            await asyncio.sleep(1)
            if i % 10 == 0:
                print(f"  Waiting... {i}s")

        if not state['sse_open']:
            print("[WARN] [STEP 4] SSE OPEN not detected within 60s (may still be working)")
        else:
            print("[OK] [STEP 4] SSE confirmed OPEN")

        # Capture baseline DOM
        baseline_html = await page.content()
        print("[STEP 5] Baseline DOM captured")

        # STEP 6: Execute replay (NOW that SSE is open)
        print("\n[STEP 6] EXECUTING REPLAY OF TEST-005...")
        print("  (This must happen AFTER SSE is OPEN)")
        replay_event_id = await replay_test005()
        if replay_event_id:
            print(f"[OK] [STEP 6] Replay published: event_id={replay_event_id}")
        else:
            print("[FAIL] [STEP 6] Replay failed")

        # STEP 7: Wait for DOM update
        print("\n[STEP 7] Waiting for DOM update without F5...")
        test005_found = False
        for i in range(30):  # Wait up to 30 seconds
            await asyncio.sleep(1)
            content = await page.content()
            if 'FRONTEND-TEST-005' in content or 'TEST-005' in content:
                test005_found = True
                print(f"[OK] [STEP 7] TEST-005 found in DOM after {i}s (NO F5)")
                break

            if i % 5 == 0 and i > 0:
                print(f"  Still waiting... {i}s")

        if not test005_found:
            print("[FAIL] [STEP 7] TEST-005 NOT found in DOM after 30s")

        # STEP 8: Capture final state
        print("\n[STEP 8] Capturing final state...")
        state['screenshot'] = await page.screenshot(path='/tmp/fase5b_final.png')
        final_html = await page.content()
        state['test005_found'] = test005_found

        # Collect console logs for analysis
        cp_logs = [log for log in state['console'] if '[REALTIME CP' in log['text']]
        print(f"\n[SUMMARY] CP logs captured: {len(cp_logs)}")
        for log in cp_logs[:15]:
            print(f"  {log['time']}: {log['text'][:70]}")

        # Final verdict
        print("\n" + "="*80)
        print("FINAL RESULT")
        print("="*80)
        print(f"SSE OPEN (CP10):     {state['sse_open']}")
        print(f"Replay published:    {replay_event_id is not None}")
        print(f"TEST-005 in DOM:     {test005_found}")
        print(f"Checkpoints logged:  {len(cp_logs)}/11")

        if state['sse_open'] and replay_event_id and test005_found:
            print("\n[OK] PASS: Real-time SSE update works without F5")
        else:
            print("\n[FAIL] FAIL: Blocker(s) detected")

        await browser.close()

        return {
            'sse_open': state['sse_open'],
            'replay_event_id': replay_event_id,
            'test005_found': test005_found,
            'checkpoints': len(cp_logs),
            'console_logs': state['console'],
            'network': state['network'],
        }


if __name__ == '__main__':
    result = asyncio.run(run_test())
    print("\n[OUTPUT] Saved to: /tmp/fase5b_final.png")
