"""
FASE 5B-A SSE Diagnosis V2 - Clean session + proper login
"""
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright


async def run_diagnosis():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        # Create FRESH context (no cached cookies)
        context = await browser.new_context()
        page = await context.new_page()

        print("\n" + "="*80)
        print("FASE 5B-A: SSE Diagnosis V2 - Clean Login")
        print("="*80 + "\n")

        sse_capture = {}
        cp10_found = False
        console_logs = []

        def on_response(response):
            if 'events/stream' in response.url:
                sse_capture['url'] = response.url
                sse_capture['status'] = response.status
                sse_capture['content_type'] = response.headers.get('content-type', 'unknown')
                print(f"[SSE RESPONSE] {response.status} | Content-Type: {sse_capture['content_type']}")
                if response.status == 200 and 'text/event-stream' in sse_capture['content_type']:
                    print("  [OK] Valid SSE response received")
                else:
                    print(f"  [FAIL] Invalid SSE response")

        def on_console(msg):
            if 'CP10' in msg.text:
                nonlocal cp10_found
                cp10_found = True
                print(f"[CP10 FOUND] {msg.text[:80]}")
            if 'error' in msg.text.lower() or 'ERROR' in msg.text:
                print(f"[CONSOLE ERROR] {msg.text[:100]}")
            console_logs.append({'type': msg.type, 'text': msg.text})

        page.on('response', on_response)
        page.on('console', on_console)

        # STEP 1: Clean navigation to login page
        print("[STEP 1] Navigate to fresh login page...")
        await page.goto('http://localhost:8001/login', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(1)

        # STEP 2: Use Django's actual login URL endpoint
        print("[STEP 2] POST to /accounts/login/ (Django standard endpoint)...")
        login_result = await page.evaluate('''
            async () => {
                try {
                    const response = await fetch('/accounts/login/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-CSRFToken': document.querySelector('[name="csrfmiddlewaretoken"]')?.value || '',
                        },
                        body: 'username=e2e_test_user&password=e2e_test_pass_12345&next=/atencion/bandeja-entrada/',
                        credentials: 'include',
                        redirect: 'manual'
                    });
                    console.log(`[LOGIN POST] ${response.status}`);
                    return { status: response.status, location: response.headers.get('location') };
                } catch (e) {
                    console.error(`[LOGIN ERROR] ${e.message}`);
                    return { error: e.message };
                }
            }
        ''')
        print(f"  Login POST result: {login_result}")

        # STEP 3: If login redirected, follow or navigate to bandeja directly
        print("[STEP 3] Navigate to bandeja-entrada...")
        if 'location' in login_result and login_result['location']:
            await page.goto(f"http://localhost:8001{login_result['location']}", wait_until='domcontentloaded', timeout=15000)
        else:
            await page.goto('http://localhost:8001/atencion/bandeja-entrada/', wait_until='domcontentloaded', timeout=15000)

        await asyncio.sleep(3)  # Wait for SSE to attempt connection

        # STEP 4: Verify authentication via API
        print("[STEP 4] Verify authentication...")
        auth_status = await page.evaluate('''
            async () => {
                try {
                    const response = await fetch('/dashboard/api/auth/check/', { credentials: 'include' });
                    const data = await response.json();
                    return { status: response.status, authenticated: data.authenticated };
                } catch (e) {
                    return { error: e.message };
                }
            }
        ''')
        print(f"  Auth status: {auth_status}")

        # STEP 5: Results
        print("\n" + "="*80)
        print("RESULTS")
        print("="*80)
        print(f"CP10 found: {cp10_found}")
        print(f"SSE response captured: {'yes' if sse_capture else 'no'}")
        if sse_capture:
            print(f"  Status: {sse_capture.get('status')}")
            print(f"  Content-Type: {sse_capture.get('content_type')}")
        print(f"Authenticated: {auth_status.get('authenticated', 'unknown')}")

        await browser.close()
        return {
            'cp10': cp10_found,
            'sse': sse_capture,
            'auth': auth_status,
        }


if __name__ == '__main__':
    asyncio.run(run_diagnosis())
