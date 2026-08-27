"""FASE G: Prepare monitoring with two tabs."""
import asyncio
from playwright.async_api import async_playwright
import json
from datetime import datetime


async def setup_tab(context, tab_name):
    """Setup a single tab with login and bandeja open."""
    page = await context.new_page()

    print(f"\n[{tab_name}] Opening login")
    await page.goto("http://localhost:8001/dashboard/login/")

    # Login
    await page.fill('input[name="username"]', "testadmin")
    await page.fill('input[name="password"]', "testpass123")
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("networkidle")

    print(f"[{tab_name}] Logged in, opening bandeja")
    await page.goto("http://localhost:8001/dashboard/whatsapp/")
    await page.wait_for_load_state("networkidle")

    # Wait for EventSource to connect
    await asyncio.sleep(3)

    print(f"[{tab_name}] Capturing baseline")

    # Get SSE status
    sse_open = await page.evaluate("""
        window.__sse_status || 'UNKNOWN'
    """)

    # Get conversaciones list
    conversaciones = await page.evaluate("""
        document.querySelectorAll('[data-conv-id]').length
    """)

    # Take screenshot
    screenshot_path = f"baseline_{tab_name}.png"
    await page.screenshot(path=screenshot_path)

    baseline = {
        "tab": tab_name,
        "timestamp": datetime.now().isoformat(),
        "sse_status": sse_open,
        "conversaciones_count": conversaciones,
        "screenshot": screenshot_path,
        "url": page.url,
    }

    print(f"[{tab_name}] Baseline: SSE={sse_open}, convs={conversaciones}")

    return page, baseline


async def main():
    """Prepare two tabs."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        # Setup tab 1 and tab 2
        page1, baseline1 = await setup_tab(context, "TAB1")
        page2, baseline2 = await setup_tab(context, "TAB2")

        print("\n" + "="*80)
        print("BASELINE CAPTURED")
        print("="*80)
        print(json.dumps([baseline1, baseline2], indent=2, default=str))

        # Keep tabs open for manual testing
        print("\nTabs ready. Waiting for user signal...")
        await asyncio.sleep(300)  # Wait 5 minutes

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
