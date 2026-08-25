"""
FASE 5B-A SSE Diagnosis - Fully automated E2E login + detailed SSE capture
No manual intervention. Resolve CP10 contradiction.
"""
import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright


async def run_diagnosis():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("\n" + "="*80)
        print("FASE 5B-A: SSE Diagnosis - Detailed Network Capture")
        print("="*80 + "\n")

        # Track all requests and responses
        requests_log = []
        responses_log = []
        sse_request = None
        sse_response = None
        console_logs = []

        def on_request(request):
            """Log all requests, especially SSE."""
            url = request.url
            log_entry = {
                'url': url,
                'method': request.method,
                'headers': dict(request.headers),
                'timestamp': datetime.now().isoformat(),
                'resource_type': request.resource_type,
            }
            requests_log.append(log_entry)

            if 'events/stream' in url:
                print(f"[REQUEST SSE] {request.method} {url}")
                print(f"  Headers: {dict(request.headers)}")
                nonlocal sse_request
                sse_request = log_entry

        def on_response(response):
            """Log all responses, especially SSE."""
            url = response.url
            log_entry = {
                'url': url,
                'status': response.status,
                'headers': dict(response.headers),
                'content_type': response.headers.get('content-type', 'unknown'),
                'timestamp': datetime.now().isoformat(),
            }
            responses_log.append(log_entry)

            if 'events/stream' in url:
                print(f"[RESPONSE SSE] {response.status} {url}")
                print(f"  Content-Type: {response.headers.get('content-type')}")
                print(f"  Headers: {dict(response.headers)}")
                nonlocal sse_response
                sse_response = log_entry

        def on_console(msg):
            """Log console messages."""
            log_entry = {
                'type': msg.type,
                'text': msg.text,
                'timestamp': datetime.now().isoformat(),
            }
            console_logs.append(log_entry)

            # Print CP10 and errors
            if 'CP10' in msg.text or 'ERROR' in msg.text or 'error' in msg.text.lower():
                print(f"[CONSOLE {msg.type.upper()}] {msg.text[:100]}")

        page.on('request', on_request)
        page.on('response', on_response)
        page.on('console', on_console)

        # STEP 1: Login
        print("[STEP 1] Automated login...")
        await page.goto('http://localhost:8001/login', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(1)

        # Get CSRF token from HTML
        csrf_token = await page.evaluate('''
            () => {
                const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
                return input ? input.value : null;
            }
        ''')
        print(f"  CSRF token obtained: {csrf_token[:20] if csrf_token else 'FAILED'}...")

        # Submit form via fetch (no manual interaction)
        login_result = await page.evaluate('''
            async (csrfToken) => {
                const form = document.querySelector('form');
                if (!form) return { success: false, error: 'form not found' };

                const formData = new FormData();
                formData.append('username', 'e2e_test_user');
                formData.append('password', 'e2e_test_pass_12345');
                if (csrfToken) formData.append('csrfmiddlewaretoken', csrfToken);

                try {
                    const response = await fetch(form.action, {
                        method: 'POST',
                        body: formData,
                        credentials: 'include',
                        redirect: 'manual'
                    });
                    console.log(`[LOGIN] Response status: ${response.status}`);
                    return {
                        success: response.ok || response.status === 302,
                        status: response.status,
                        url: response.url
                    };
                } catch (e) {
                    return { success: false, error: e.message };
                }
            }
        ''', csrf_token)

        print(f"  Login response: {login_result}")
        await asyncio.sleep(1)

        # Verify authentication by checking /dashboard
        try:
            await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded', timeout=10000)
            dashboard_title = await page.title()
            print(f"  Dashboard loaded: {dashboard_title[:50]}")
        except Exception as e:
            print(f"  Dashboard load failed: {str(e)[:80]}")

        # STEP 2: Navigate to bandeja and capture SSE
        print("\n[STEP 2] Navigate to bandeja + capture SSE request/response...")
        await page.goto('http://localhost:8001/atencion/bandeja-entrada/', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(3)  # Allow SSE to connect

        # STEP 3: Verify CP10
        print("\n[STEP 3] Check for CP10...")
        cp10_found = False
        for log in console_logs:
            if 'CP10' in log['text']:
                cp10_found = True
                print(f"  [CP10 FOUND] {log['text'][:80]}")
                break

        if not cp10_found:
            print("  [CP10 NOT FOUND] in console logs")

        # STEP 4: Report findings
        print("\n" + "="*80)
        print("DIAGNOSIS RESULTS")
        print("="*80)

        print("\n[SSE REQUEST]")
        if sse_request:
            print(f"  URL: {sse_request['url']}")
            print(f"  Method: {sse_request['method']}")
            print(f"  Resource Type: {sse_request['resource_type']}")
            # Don't print full headers but do list key ones
            if 'authorization' in sse_request['headers']:
                print(f"  Authorization: [PRESENT]")
            if 'cookie' in sse_request['headers']:
                print(f"  Cookie: [PRESENT, length={len(sse_request['headers']['cookie'])}]")
        else:
            print("  [NOT CAPTURED] SSE request never made")

        print("\n[SSE RESPONSE]")
        if sse_response:
            print(f"  Status: {sse_response['status']}")
            print(f"  Content-Type: {sse_response['content_type']}")
            print(f"  Cache-Control: {sse_response['headers'].get('cache-control', 'NOT SET')}")
            print(f"  X-Accel-Buffering: {sse_response['headers'].get('x-accel-buffering', 'NOT SET')}")

            if sse_response['status'] == 200 and 'text/event-stream' in sse_response['content_type']:
                print("  [OK] Valid SSE response 200 + text/event-stream")
            else:
                print(f"  [INVALID] Not a valid SSE response")
        else:
            print("  [NOT CAPTURED] SSE response never received")

        print("\n[CP10 STATUS]")
        print(f"  CP10 in console logs: {cp10_found}")

        print("\n[CONTRADICTION CHECK]")
        if cp10_found and sse_response and sse_response['status'] == 200 and 'text/event-stream' in sse_response['content_type']:
            print("  VALID: CP10=True matches SSE 200 + text/event-stream")
            print("  SSE connection WAS successful")
        elif cp10_found and not sse_response:
            print("  PROBLEM: CP10=True but no SSE response captured")
            print("  Possible: Response came from elsewhere (cached? different URL?)")
        elif cp10_found and sse_response and sse_response['status'] != 200:
            print(f"  PROBLEM: CP10=True but SSE status={sse_response['status']} (not 200)")
            print("  Possible: EventSource opened from error response")
        else:
            print("  VALID: CP10=False matches no SSE response")

        print("\n[ALL REQUESTS]")
        for req in requests_log:
            if 'events' in req['url'] or 'api' in req['url']:
                print(f"  {req['method']} {req['url']} ({req['resource_type']})")

        print("\n[ALL RESPONSES]")
        for resp in responses_log:
            if 'events' in resp['url'] or 'api' in resp['url']:
                print(f"  {resp['status']} {resp['url']} ({resp['content_type']})")

        await browser.close()

        return {
            'cp10_found': cp10_found,
            'sse_request': sse_request,
            'sse_response': sse_response,
            'console_logs_count': len(console_logs),
            'requests_count': len(requests_log),
            'responses_count': len(responses_log),
        }


if __name__ == '__main__':
    result = asyncio.run(run_diagnosis())
    print("\n[DIAGNOSIS COMPLETE]")
    print(f"CP10: {result['cp10_found']}")
    print(f"SSE Request: {'CAPTURED' if result['sse_request'] else 'MISSING'}")
    print(f"SSE Response: {'CAPTURED' if result['sse_response'] else 'MISSING'}")
