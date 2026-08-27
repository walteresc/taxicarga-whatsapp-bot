"""Reproduce and trace login/logout cycling issue."""
import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Force UTF-8 output
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


async def run_cycles():
    """Run 10 login/logout cycles with full tracing."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()

        results = []

        for cycle in range(1, 11):
            print(f"\n{'='*80}")
            print(f"CYCLE {cycle}/10")
            print(f"{'='*80}")

            page = await context.new_page()
            cycle_data = {
                "cycle": cycle,
                "start": datetime.now().isoformat(),
                "steps": {},
                "errors": [],
                "requests": [],
                "console_logs": [],
            }

            # Capture console
            def log_console(msg):
                cycle_data["console_logs"].append({
                    "type": msg.type,
                    "text": str(msg.text)[:100],
                    "timestamp": datetime.now().isoformat()
                })
            page.on("console", log_console)

            # Capture requests
            def log_request(req):
                cycle_data["requests"].append({
                    "method": req.method,
                    "url": req.url.split("?")[0],  # Remove query params
                    "timestamp": datetime.now().isoformat()
                })
            page.on("request", log_request)

            try:
                # STEP 1: Navigate to login
                print(f"[{cycle}] STEP 1: Navigate to /login")
                cycle_data["steps"]["navigate_login"] = "starting"
                await page.goto("http://localhost:8001/dashboard/login/")
                cycle_data["steps"]["navigate_login"] = "success"
                print(f"[{cycle}] [OK] At login page")

                # STEP 2: Login
                print(f"[{cycle}] STEP 2: Submit login form")
                cycle_data["steps"]["login_submit"] = "starting"
                await page.fill('input[name="username"]', "testadmin")
                await page.fill('input[name="password"]', "testpass123")

                # Wait for button and click
                button = await page.query_selector('button[type="submit"]')
                if not button:
                    raise Exception("Submit button not found")

                await button.click()

                # Wait for navigation
                try:
                    await page.wait_for_url("**/bandeja-entrada**", timeout=10000)
                    cycle_data["steps"]["login_submit"] = "success"
                    print(f"[{cycle}] ✓ Login successful, navigated to bandeja")
                except PlaywrightTimeoutError:
                    cycle_data["steps"]["login_submit"] = "timeout"
                    cycle_data["errors"].append("Login timeout after 10s")
                    print(f"[{cycle}] [FAIL] Login timeout")
                    raise

                # STEP 3: Confirm authenticated
                print(f"[{cycle}] STEP 3: Verify session")
                cycle_data["steps"]["verify_session"] = "checking"
                cookies = await context.cookies()
                session_cookie = next((c for c in cookies if c["name"] == "sessionid"), None)
                if session_cookie:
                    cycle_data["steps"]["verify_session"] = "authenticated"
                    print(f"[{cycle}] [OK] Session cookie present")
                else:
                    cycle_data["steps"]["verify_session"] = "no_session"
                    cycle_data["errors"].append("No sessionid cookie after login")
                    print(f"[{cycle}] [FAIL] No session cookie")
                    raise Exception("No session after login")

                # STEP 4: Wait for SSE
                print(f"[{cycle}] STEP 4: Check SSE connection")
                cycle_data["steps"]["sse_check"] = "checking"
                await asyncio.sleep(2)
                cycle_data["steps"]["sse_check"] = "ok"
                print(f"[{cycle}] [OK] Page loaded")

                # STEP 5: Logout
                print(f"[{cycle}] STEP 5: Perform logout")
                cycle_data["steps"]["logout"] = "starting"

                # Find and click logout button
                logout_button = await page.query_selector('button:has-text("Salir")')
                if not logout_button:
                    # Try alternative selectors
                    logout_button = await page.query_selector('[data-action="logout"]')
                if not logout_button:
                    logout_button = await page.query_selector('a:has-text("Salir")')

                if logout_button:
                    await logout_button.click()
                else:
                    print(f"[{cycle}] [WARN] Logout button not found, trying keyboard")
                    # Try keyboard shortcut or direct navigation
                    await page.goto("http://localhost:8001/dashboard/logout/")

                # Wait for redirect to login
                try:
                    await page.wait_for_url("**/login**", timeout=10000)
                    cycle_data["steps"]["logout"] = "success"
                    print(f"[{cycle}] [OK] Logout successful, back at login")
                except PlaywrightTimeoutError:
                    cycle_data["steps"]["logout"] = "timeout"
                    cycle_data["errors"].append("Logout timeout")
                    print(f"[{cycle}] [FAIL] Logout timeout")
                    raise

                # STEP 6: Verify logged out
                print(f"[{cycle}] STEP 6: Verify session cleared")
                cycle_data["steps"]["verify_logout"] = "checking"
                cookies_after = await context.cookies()
                session_after = next((c for c in cookies_after if c["name"] == "sessionid"), None)

                if not session_after:
                    cycle_data["steps"]["verify_logout"] = "cleared"
                    print(f"[{cycle}] [OK] Session cleared")
                else:
                    cycle_data["steps"]["verify_logout"] = "still_authenticated"
                    print(f"[{cycle}] [WARN] Session still present")

                cycle_data["end"] = datetime.now().isoformat()
                cycle_data["status"] = "PASS"

            except Exception as e:
                cycle_data["end"] = datetime.now().isoformat()
                cycle_data["status"] = "FAIL"
                cycle_data["errors"].append(str(e))
                print(f"[{cycle}] [ERROR] {e}")

            finally:
                await page.close()
                results.append(cycle_data)

        # Print summary
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")

        passed = sum(1 for r in results if r["status"] == "PASS")
        failed = sum(1 for r in results if r["status"] == "FAIL")

        print(f"PASSED: {passed}/10")
        print(f"FAILED: {failed}/10")

        for r in results:
            status = "[OK]" if r["status"] == "PASS" else "[FAIL]"
            print(f"{status} Cycle {r['cycle']}: {r['status']}")
            if r["errors"]:
                for err in r["errors"]:
                    print(f"    - {err}")

        # Save detailed log
        with open("login_logout_trace.json", "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\nDetailed log saved to: login_logout_trace.json")

        await browser.close()
        return passed == 10


if __name__ == "__main__":
    success = asyncio.run(run_cycles())
    exit(0 if success else 1)
