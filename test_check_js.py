"""Verify what JS files are loaded."""
import asyncio
from playwright.async_api import async_playwright
import requests


async def test():
    session = requests.Session()
    resp = session.post(
        'http://localhost:8001/dashboard/api/auth/login/',
        json={'username': 'e2e_test', 'password': 'e2e_test_password'}
    )
    sessionid = session.cookies.get_dict().get('sessionid')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await ctx.new_page()

        await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        await asyncio.sleep(2)

        # Get all script sources
        scripts = await page.evaluate("""
        () => {
          const scripts = Array.from(document.querySelectorAll('script[src]'));
          return scripts.map(s => s.src).filter(src => src.includes('index-') || src.includes('default-'));
        }
        """)

        print("JS files loaded:")
        for src in scripts:
            print(f"  {src}")

        # Check if the build hash matches
        if scripts:
            latest = scripts[-1]
            print(f"\nLatest JS file: {latest}")

            # Extract hash from filename
            import re
            match = re.search(r'([A-Za-z0-9]+)\.js', latest)
            if match:
                build_hash = match.group(1)
                print(f"Build hash: {build_hash}")

        await ctx.close()
        await browser.close()


asyncio.run(test())
