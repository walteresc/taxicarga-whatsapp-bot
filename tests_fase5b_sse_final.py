"""
FASE 5B-A SSE Final Diagnosis - API login endpoint
Resolve contradiction: CP10 vs. Django SSE response
"""
import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright


async def run_final():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("\n" + "="*80)
        print("FASE 5B-A: FINAL SSE DIAGNOSIS - API Login")
        print("="*80 + "\n")

        sse_data = {}
        cp10 = False
        auth = False

        def on_response(response):
            if 'events/stream' in response.url:
                sse_data['status'] = response.status
                sse_data['content_type'] = response.headers.get('content-type', '')
                print(f"[SSE] {response.status} | {sse_data['content_type']}")

        def on_console(msg):
            nonlocal cp10
            if 'CP10' in msg.text:
                cp10 = True
                print(f"[CP10] DETECTED")

        page.on('response', on_response)
        page.on('console', on_console)

        # STEP 1: Start blank page
        print("[1] Loading blank page...")
        await page.goto('http://localhost:8001/', wait_until='domcontentloaded')
        await asyncio.sleep(1)

        # STEP 2: Login via API
        print("[2] Login via /dashboard/api/auth/login/...")
        login_result = await page.evaluate('''
            async () => {
                const response = await fetch('/dashboard/api/auth/login/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: 'e2e_test_user', password: 'e2e_test_pass_12345' }),
                    credentials: 'include'
                });
                const data = await response.json();
                console.log(`[LOGIN] ${response.status}: ${data.user?.username || data.error}`);
                return { status: response.status, username: data.user?.username };
            }
        ''')
        print(f"  Result: {login_result}")
        if login_result.get('username'):
            auth = True

        # STEP 3: Check auth
        print("[3] Verify authentication...")
        auth_check = await page.evaluate('''
            async () => {
                const response = await fetch('/dashboard/api/auth/check/', { credentials: 'include' });
                const data = await response.json();
                console.log(`[AUTH_CHECK] authenticated=${data.authenticated}`);
                return data.authenticated;
            }
        ''')
        if auth_check:
            auth = True

        # STEP 4: Navigate to bandeja
        print("[4] Navigate to bandeja-entrada...")
        await page.goto('http://localhost:8001/atencion/bandeja-entrada/', wait_until='domcontentloaded')
        await asyncio.sleep(4)

        # RESULTS
        print("\n" + "="*80)
        print("FINAL RESULTS")
        print("="*80)
        print(f"Authentication: {'SUCCESS' if auth else 'FAILED'}")
        print(f"CP10 (EventSource.onopen): {'YES' if cp10 else 'NO'}")
        if sse_data:
            print(f"SSE Response: {sse_data['status']} | {sse_data['content_type']}")
            if sse_data['status'] == 200 and 'text/event-stream' in sse_data['content_type']:
                print("  [VALID SSE]")
            else:
                print("  [INVALID SSE]")
        else:
            print("SSE Response: NOT CAPTURED")

        print("\n[CONTRADICTION RESOLUTION]")
        if auth and cp10 and sse_data.get('status') == 200:
            print("RESOLVED: CP10=True + SSE 200 = EventSource.onopen was called with valid stream")
            print("Status: FASE 5B-A READY TO PROCEED")
        elif auth and not cp10 and sse_data.get('status') != 200:
            print("RESOLVED: CP10=False + SSE non-200 = EventSource got redirect, onopen never fired")
            print("Status: AUTHENTICATION/AUTHORIZATION ISSUE")
        elif not auth:
            print("ROOT CAUSE: User not authenticated, SSE endpoint returns 302 redirect")
            print("Status: FIX LOGIN, THEN RETRY")
        else:
            print(f"AMBIGUOUS: auth={auth}, cp10={cp10}, status={sse_data.get('status')}")

        await browser.close()


if __name__ == '__main__':
    asyncio.run(run_final())
