"""
FASE 5B-A SIMPLIFIED: Verificar bloqueo en Tab 1
Ejecutar individual y luego ambas
"""
import asyncio
import subprocess
import os
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
        if 'event_id=' in result.stdout or 'event_id=' in result.stderr:
            import re
            match = re.search(r'event_id=([0-9-]+)', result.stdout + result.stderr)
            if match:
                return match.group(1)
        return None
    except:
        return None


async def test_single_tab(tab_num, browser):
    """Test single tab in isolation"""
    context = await browser.new_context()
    page = await context.new_page()

    sse_open = False
    test_found = False

    def on_console(msg):
        nonlocal sse_open
        if '[REALTIME CP10]' in msg.text:
            sse_open = True

    page.on('console', on_console)

    print(f"\n  [SINGLE-{tab_num}] Navigate login...")
    await page.goto('http://localhost:8001/login', wait_until='domcontentloaded', timeout=15000)
    await asyncio.sleep(2)

    print(f"  [SINGLE-{tab_num}] Submit login...")
    await page.evaluate('''
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
    await page.goto('http://localhost:8001/atencion/bandeja-entrada/', wait_until='domcontentloaded', timeout=15000)
    await asyncio.sleep(2)

    print(f"  [SINGLE-{tab_num}] Waiting for SSE OPEN...")
    for i in range(60):
        if sse_open:
            print(f"  [SINGLE-{tab_num}] SSE OPEN at {i}s")
            break
        await asyncio.sleep(1)

    if not sse_open:
        print(f"  [SINGLE-{tab_num}] SSE FAILED")
        await context.close()
        return False

    print(f"  [SINGLE-{tab_num}] Executing replay...")
    event_id = await replay()
    print(f"  [SINGLE-{tab_num}] Replay event_id: {event_id}")

    print(f"  [SINGLE-{tab_num}] Waiting for TEST-005...")
    for i in range(30):
        content = await page.content()
        if 'TEST-005' in content or 'FRONTEND-TEST-005' in content:
            test_found = True
            print(f"  [SINGLE-{tab_num}] TEST-005 found at {i}s")
            break
        await asyncio.sleep(1)

    if not test_found:
        print(f"  [SINGLE-{tab_num}] TEST-005 NOT found")

    await context.close()
    return test_found


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        print("="*80)
        print("FASE 5B-A SIMPLIFIED: Test individual tabs first")
        print("="*80)

        print("\n[PHASE 1] Testing Tab 1 alone...")
        tab1_alone = await test_single_tab(1, browser)
        print(f"  Result: {'PASS' if tab1_alone else 'FAIL'}")

        print("\n[PHASE 2] Testing Tab 2 alone...")
        tab2_alone = await test_single_tab(2, browser)
        print(f"  Result: {'PASS' if tab2_alone else 'FAIL'}")

        # If both pass individually, test together
        if tab1_alone and tab2_alone:
            print("\n[PHASE 3] Testing both tabs simultaneously...")
            print("  (Opening both tabs, both should receive same replay event)")

            context1 = await browser.new_context()
            context2 = await browser.new_context()
            page1 = await context1.new_page()
            page2 = await context2.new_page()

            sse1 = False
            sse2 = False
            found1 = False
            found2 = False

            def make_handlers(page_num):
                def on_console(msg):
                    nonlocal sse1, sse2
                    if '[REALTIME CP10]' in msg.text:
                        if page_num == 1:
                            sse1 = True
                        else:
                            sse2 = True
                return on_console

            page1.on('console', make_handlers(1))
            page2.on('console', make_handlers(2))

            # Login both
            for page in [page1, page2]:
                await page.goto('http://localhost:8001/login', wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(1)
                await page.evaluate('''
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
                await asyncio.sleep(1)

            # Navigate both
            for page in [page1, page2]:
                await page.goto('http://localhost:8001/atencion/bandeja-entrada/', wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(1)

            # Wait for both SSE
            print("  Waiting for both SSE OPEN...")
            for i in range(60):
                if sse1 and sse2:
                    print(f"  Both SSE OPEN at {i}s")
                    break
                await asyncio.sleep(1)

            if not (sse1 and sse2):
                print(f"  SSE failure: sse1={sse1}, sse2={sse2}")
            else:
                # Replay once
                print("  Executing single replay...")
                event_id = await replay()
                print(f"  Replay event_id: {event_id}")

                # Wait for both to receive
                print("  Waiting for both to receive...")
                for i in range(30):
                    c1 = await page1.content()
                    c2 = await page2.content()
                    found1 = 'TEST-005' in c1 or 'FRONTEND-TEST-005' in c1
                    found2 = 'TEST-005' in c2 or 'FRONTEND-TEST-005' in c2

                    if found1 and found2:
                        print(f"  BOTH received at {i}s")
                        break
                    elif found1 or found2:
                        print(f"  Partial: found1={found1}, found2={found2} at {i}s")

                    await asyncio.sleep(1)

                print(f"  Final: found1={found1}, found2={found2}")

            await context1.close()
            await context2.close()
        else:
            print("\n[PHASE 3] SKIPPED: Individual tabs failed, cannot test simultaneous")

        await browser.close()

        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Tab 1 solo: {'PASS' if tab1_alone else 'FAIL'}")
        print(f"Tab 2 solo: {'PASS' if tab2_alone else 'FAIL'}")


if __name__ == '__main__':
    asyncio.run(run())
