"""
FASE 5B-A: Two-tab real-time sync test - AUTHORIZED USER
Strict order: Browser1 -> Login -> SSE OPEN -> Baseline
            Browser2 -> Login -> SSE OPEN -> Baseline
            Replay 1x -> Both receive without F5
"""
import asyncio
import subprocess
import os
from datetime import datetime
from playwright.async_api import async_playwright


async def replay():
    try:
        result = subprocess.run(
            ['docker-compose', 'exec', '-T', 'django', 'python', 'manage.py', 'replay_test005'],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=10
        )
        if 'event_id=' in result.stdout + result.stderr:
            import re
            m = re.search(r'event_id=([0-9-]+)', result.stdout + result.stderr)
            return m.group(1) if m else None
        return None
    except:
        return None


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx1 = await browser.new_context()
        ctx2 = await browser.new_context()
        page1 = await ctx1.new_page()
        page2 = await ctx2.new_page()

        print("\n" + "="*80)
        print("FASE 5B-A: Two Tabs Real-time Sync")
        print("="*80 + "\n")

        sse1 = sse2 = False
        found1 = found2 = False

        def mk_handlers(page_num):
            def on_console(msg):
                if 'CP10' in msg.text:
                    if page_num == 1:
                        nonlocal sse1
                        sse1 = True
                        print(f"[TAB 1] SSE OPEN")
                    else:
                        nonlocal sse2
                        sse2 = True
                        print(f"[TAB 2] SSE OPEN")
            return on_console

        page1.on('console', mk_handlers(1))
        page2.on('console', mk_handlers(2))

        async def login_and_navigate(page, tab_num):
            """Login and navigate to bandeja for a page."""
            # Start blank
            await page.goto('http://localhost:8001/', wait_until='domcontentloaded')
            # API login
            await page.evaluate('''
                async () => {
                    await fetch('/dashboard/api/auth/login/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username: 'e2e_test_user', password: 'e2e_test_pass_12345' }),
                        credentials: 'include'
                    });
                }
            ''')
            await asyncio.sleep(1)
            # Navigate to bandeja
            await page.goto('http://localhost:8001/atencion/bandeja-entrada/', wait_until='domcontentloaded')
            print(f"[TAB {tab_num}] Navigated to bandeja")

        # LOGIN BOTH
        print("[STEP 1] Login and navigate both tabs...")
        await asyncio.gather(
            login_and_navigate(page1, 1),
            login_and_navigate(page2, 2)
        )

        # WAIT FOR SSE OPEN
        print("[STEP 2] Waiting for SSE OPEN in both tabs...")
        for i in range(60):
            if sse1 and sse2:
                print(f"[OK] Both SSE OPEN at {i}s")
                break
            await asyncio.sleep(1)

        if not (sse1 and sse2):
            print(f"[FAIL] SSE status: tab1={sse1}, tab2={sse2}")

        # EXECUTE REPLAY
        print("[STEP 3] Execute single replay...")
        event_id = await replay()
        print(f"[REPLAY] event_id={event_id}")

        # WAIT FOR DOM UPDATE
        print("[STEP 4] Waiting for both to receive TEST-005...")
        for i in range(30):
            if not found1:
                c1 = await page1.content()
                found1 = 'TEST-005' in c1 or 'FRONTEND-TEST-005' in c1
            if not found2:
                c2 = await page2.content()
                found2 = 'TEST-005' in c2 or 'FRONTEND-TEST-005' in c2

            if found1 and found2:
                print(f"[OK] Both received at {i}s")
                break
            elif found1 or found2:
                print(f"[PARTIAL] found1={found1}, found2={found2} at {i}s")
            await asyncio.sleep(1)

        # RESULTS
        print("\n" + "="*80)
        print("FASE 5B-A RESULTS")
        print("="*80)
        print(f"Tab 1 SSE OPEN: {sse1}")
        print(f"Tab 2 SSE OPEN: {sse2}")
        print(f"Tab 1 TEST-005: {found1}")
        print(f"Tab 2 TEST-005: {found2}")

        if sse1 and sse2 and found1 and found2:
            print("\n[PASS] FASE 5B-A: Two-tab synchronization works without F5")
        else:
            print("\n[FAIL] Some blockers detected")

        await browser.close()


if __name__ == '__main__':
    asyncio.run(run())
