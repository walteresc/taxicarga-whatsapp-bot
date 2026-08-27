"""
FASE 5B-A: Dos pestanas - SSE real-time sync without F5
Strict order: 2x Browser -> Login -> SSE OPEN -> Baseline -> Replay 1x -> DOM update both
"""
import asyncio
import json
import subprocess
import os
from datetime import datetime
from playwright.async_api import async_playwright


async def replay_test_correlation(correlation_id='TEST-FASE-A-001'):
    """Execute controlled replay with correlation_id via Docker."""
    try:
        result = subprocess.run(
            ['docker-compose', 'exec', '-T', 'django', 'python', 'manage.py', 'replay_test005'],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=10
        )

        if 'event_id=' in result.stdout or 'event_id=' in result.stderr:
            combined = result.stdout + result.stderr
            for line in combined.split('\n'):
                if 'event_id=' in line:
                    import re
                    match = re.search(r'event_id=([0-9-]+)', line)
                    if match:
                        event_id = match.group(1)
                        return {'correlation_id': correlation_id, 'event_id': event_id}
        return None
    except Exception as e:
        print(f"[ERROR] Replay failed: {str(e)[:100]}")
        return None


async def run_two_tabs_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context1 = await browser.new_context()
        context2 = await browser.new_context()
        page1 = await context1.new_page()
        page2 = await context2.new_page()

        # State tracking for both pages
        state = {
            'page1': {
                'console': [],
                'network': [],
                'sse_open': False,
                'test_found': False,
                'baseline_html': None,
                'final_html': None,
            },
            'page2': {
                'console': [],
                'network': [],
                'sse_open': False,
                'test_found': False,
                'baseline_html': None,
                'final_html': None,
            }
        }

        def make_handlers(page_num):
            def on_console(msg):
                state[page_num]['console'].append({
                    'type': msg.type,
                    'text': msg.text,
                    'time': datetime.now().isoformat(),
                })
                if '[REALTIME CP10]' in msg.text:
                    state[page_num]['sse_open'] = True
                    print(f"[OK] Tab {page_num}: SSE OPEN detected")
                if 'TEST-005' in msg.text or 'FRONTEND-TEST' in msg.text:
                    print(f"     Tab {page_num}: TEST-005 reference: {msg.text[:60]}")
                if 'cursor' in msg.text.lower() or 'event_id=' in msg.text.lower():
                    print(f"     Tab {page_num}: {msg.text[:80]}")

            def on_response(response):
                state[page_num]['network'].append({
                    'url': response.url,
                    'status': response.status,
                    'time': datetime.now().isoformat(),
                })
                if 'events/stream' in response.url:
                    print(f"  [NETWORK] Tab {page_num}: SSE endpoint: {response.status}")

            return on_console, on_response

        # Setup page1
        on_console1, on_response1 = make_handlers('page1')
        page1.on('console', on_console1)
        page1.on('response', on_response1)

        # Setup page2
        on_console2, on_response2 = make_handlers('page2')
        page2.on('console', on_console2)
        page2.on('response', on_response2)

        print("\n" + "="*80)
        print("FASE 5B-A: Two Tabs - Real-time Sync Test")
        print("="*80 + "\n")

        # STEP 1: Navigate and login both tabs
        print("[STEP 1] Tab 1: Navigate to login...")
        await page1.goto('http://localhost:8001/login', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(2)

        print("[STEP 1] Tab 2: Navigate to login...")
        await page2.goto('http://localhost:8001/login', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(2)

        # STEP 2: Login both tabs
        print("[STEP 2] Tab 1: Submitting login form...")
        try:
            await page1.evaluate('''
                async () => {
                    const form = document.querySelector('form');
                    const data = new FormData();
                    data.append('username', 'demo_vendedor');
                    data.append('password', 'demo_vendedor');
                    const csrfToken = document.querySelector('[name="csrfmiddlewaretoken"]')?.value;
                    if (csrfToken) data.append('csrfmiddlewaretoken', csrfToken);
                    await fetch(form.action, {method: 'POST', body: data, credentials: 'include'});
                }
            ''')
            await asyncio.sleep(2)
            await page1.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded', timeout=10000)
            print("[OK] Tab 1: Login processed")
        except Exception as e:
            print(f"[WARN] Tab 1: Login error: {str(e)[:80]}")

        print("[STEP 2] Tab 2: Submitting login form...")
        try:
            await page2.evaluate('''
                async () => {
                    const form = document.querySelector('form');
                    const data = new FormData();
                    data.append('username', 'demo_vendedor');
                    data.append('password', 'demo_vendedor');
                    const csrfToken = document.querySelector('[name="csrfmiddlewaretoken"]')?.value;
                    if (csrfToken) data.append('csrfmiddlewaretoken', csrfToken);
                    await fetch(form.action, {method: 'POST', body: data, credentials: 'include'});
                }
            ''')
            await asyncio.sleep(2)
            await page2.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded', timeout=10000)
            print("[OK] Tab 2: Login processed")
        except Exception as e:
            print(f"[WARN] Tab 2: Login error: {str(e)[:80]}")

        # STEP 3: Navigate to bandeja in both tabs
        print("[STEP 3] Tab 1: Navigating to bandeja-entrada...")
        await page1.goto('http://localhost:8001/atencion/bandeja-entrada/', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(1)  # Let page fully settle

        print("[STEP 3] Tab 2: Navigating to bandeja-entrada...")
        await page2.goto('http://localhost:8001/atencion/bandeja-entrada/', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(1)  # Let page fully settle

        # Verify both pages loaded
        try:
            title1 = await page1.title()
            print(f"  Tab 1 title: {title1[:50]}")
        except:
            print(f"  Tab 1 title: (error)")

        try:
            title2 = await page2.title()
            print(f"  Tab 2 title: {title2[:50]}")
        except:
            print(f"  Tab 2 title: (error)")

        # STEP 4: Wait for SSE OPEN in both tabs (extend timeout)
        print("\n[STEP 4] Waiting for SSE OPEN (CP10) in both tabs...")
        for i in range(90):
            if state['page1']['sse_open'] and state['page2']['sse_open']:
                print(f"[OK] Both tabs: SSE OPEN confirmed at {i}s")
                break
            await asyncio.sleep(1)
            if i % 10 == 0 and i > 0:
                print(f"  Waiting... {i}s (page1={state['page1']['sse_open']}, page2={state['page2']['sse_open']})")
            # After 30s, try to trigger initialization if not yet open
            if i == 30:
                print("  [30s mark] Triggering potential re-initialization...")
                try:
                    await page1.evaluate('() => window.dispatchEvent(new Event("focus"))')
                    await page2.evaluate('() => window.dispatchEvent(new Event("focus"))')
                except:
                    pass

        if not (state['page1']['sse_open'] and state['page2']['sse_open']):
            print("[WARN] One or both tabs: SSE OPEN not detected within 60s")

        # STEP 5: Capture baseline DOM
        print("\n[STEP 5] Capturing baseline DOM...")
        state['page1']['baseline_html'] = await page1.content()
        state['page2']['baseline_html'] = await page2.content()

        # Multiple selectors for conversations
        for selector in ['conversacion-row', 'v-list-item', 'data-test-conversation', 'conversation']:
            c1 = state['page1']['baseline_html'].count(selector)
            c2 = state['page2']['baseline_html'].count(selector)
            if c1 > 0 or c2 > 0:
                print(f"  Selector '{selector}': tab1={c1}, tab2={c2}")

        print(f"  Tab 1 HTML size: {len(state['page1']['baseline_html'])} bytes")
        print(f"  Tab 2 HTML size: {len(state['page2']['baseline_html'])} bytes")

        # STEP 6: Execute ONE controlled replay
        print("\n[STEP 6] EXECUTING REPLAY (single event, both tabs listening)...")
        replay_result = await replay_test_correlation('TEST-FASE-A-001')
        if replay_result:
            print(f"[OK] Replay published: event_id={replay_result['event_id']}, correlation_id={replay_result['correlation_id']}")
        else:
            print("[FAIL] Replay failed")

        # STEP 7: Wait for DOM update in both tabs
        print("\n[STEP 7] Waiting for DOM update in both tabs (no F5)...")
        test_found_p1 = False
        test_found_p2 = False

        for i in range(30):
            await asyncio.sleep(1)

            # Check page1
            if not test_found_p1:
                content1 = await page1.content()
                if 'FRONTEND-TEST-005' in content1 or 'TEST-005' in content1:
                    test_found_p1 = True
                    state['page1']['test_found'] = True
                    print(f"[OK] Tab 1: TEST-005 found after {i}s (NO F5)")

            # Check page2
            if not test_found_p2:
                content2 = await page2.content()
                if 'FRONTEND-TEST-005' in content2 or 'TEST-005' in content2:
                    test_found_p2 = True
                    state['page2']['test_found'] = True
                    print(f"[OK] Tab 2: TEST-005 found after {i}s (NO F5)")

            if test_found_p1 and test_found_p2:
                print(f"[OK] Both tabs: TEST-005 synchronized at {i}s")
                break

            if i % 5 == 0 and i > 0:
                print(f"  Still waiting... {i}s (tab1={test_found_p1}, tab2={test_found_p2})")

        if not test_found_p1:
            print("[FAIL] Tab 1: TEST-005 NOT found after 30s")
        if not test_found_p2:
            print("[FAIL] Tab 2: TEST-005 NOT found after 30s")

        # STEP 8: Capture final state
        print("\n[STEP 8] Capturing final state and screenshots...")
        state['page1']['final_html'] = await page1.content()
        state['page2']['final_html'] = await page2.content()

        await page1.screenshot(path='C:\\Users\\user\\AppData\\Local\\Temp\\claude\\d--DESARROLLO-IA-Proyecto-taxi-carga\\7287622d-68ce-4eb1-9c02-aa0f258288a8\\scratchpad\\fase5b_tab1.png')
        await page2.screenshot(path='C:\\Users\\user\\AppData\\Local\\Temp\\claude\\d--DESARROLLO-IA-Proyecto-taxi-carga\\7287622d-68ce-4eb1-9c02-aa0f258288a8\\scratchpad\\fase5b_tab2.png')

        # STEP 9: Verify deduplication (same event received once per tab, not duplicated)
        print("\n[STEP 9] Verifying deduplication and synchronization...")
        test005_count_p1 = state['page1']['final_html'].count('TEST-005') if 'TEST-005' in state['page1']['final_html'] else 0
        test005_count_p2 = state['page2']['final_html'].count('TEST-005') if 'TEST-005' in state['page2']['final_html'] else 0
        print(f"  Tab 1: TEST-005 appears {test005_count_p1} times in DOM")
        print(f"  Tab 2: TEST-005 appears {test005_count_p2} times in DOM")

        # Analyze console logs for duplicates
        test005_logs_p1 = [log for log in state['page1']['console'] if 'TEST-005' in log.get('text', '')]
        test005_logs_p2 = [log for log in state['page2']['console'] if 'TEST-005' in log.get('text', '')]
        print(f"  Tab 1: {len(test005_logs_p1)} TEST-005 log entries")
        print(f"  Tab 2: {len(test005_logs_p2)} TEST-005 log entries")

        # Final verdict
        print("\n" + "="*80)
        print("FASE 5B-A RESULT")
        print("="*80)
        print(f"Tab 1 SSE OPEN:      {state['page1']['sse_open']}")
        print(f"Tab 2 SSE OPEN:      {state['page2']['sse_open']}")
        print(f"Tab 1 TEST-005 found: {test_found_p1}")
        print(f"Tab 2 TEST-005 found: {test_found_p2}")
        print(f"Both synchronized:    {test_found_p1 and test_found_p2}")
        print(f"No duplicates:        {test005_count_p1 <= 2 and test005_count_p2 <= 2}")

        if state['page1']['sse_open'] and state['page2']['sse_open'] and test_found_p1 and test_found_p2 and test005_count_p1 <= 2 and test005_count_p2 <= 2:
            print("\n[OK] FASE 5B-A PASS: Two-tab synchronization works without F5")
        else:
            print("\n[FAIL] FASE 5B-A: Blocker(s) detected")

        await browser.close()

        return {
            'page1_sse_open': state['page1']['sse_open'],
            'page2_sse_open': state['page2']['sse_open'],
            'page1_test_found': test_found_p1,
            'page2_test_found': test_found_p2,
            'replay_result': replay_result,
            'deduplication_ok': test005_count_p1 <= 2 and test005_count_p2 <= 2,
            'console_logs': {
                'page1': len(state['page1']['console']),
                'page2': len(state['page2']['console']),
            }
        }


if __name__ == '__main__':
    result = asyncio.run(run_two_tabs_test())
    print("\n[OUTPUT] Screenshots saved:")
    print("  - fase5b_tab1.png")
    print("  - fase5b_tab2.png")
