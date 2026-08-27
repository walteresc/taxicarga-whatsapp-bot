#!/usr/bin/env python
"""FASE A: SSE Open + Event Publish Timing Test

1. Open SSE in two tabs
2. Wait 5 seconds for generator initialization
3. Publish event
4. Check if both tabs receive event within 3 seconds

Hypothesis: Event must be published AFTER SSE generator opens
"""

import asyncio
import time
from playwright.async_api import async_playwright
import subprocess
import json

async def main():
    print("=" * 80)
    print("FASE A: SSE Timing Test (Event published AFTER SSE opens)")
    print("=" * 80)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/.playwright_profile",
            no_viewport=True,
            channel="chrome"
        )

        # Login and navigate
        print("\n[STEP 1] Login both tabs...")
        page1 = await context.new_page()
        page2 = await context.new_page()

        # Login page 1
        await page1.goto("http://localhost:8001/login")
        await page1.fill('input[name="username"]', "testadmin")
        await page1.fill('input[name="password"]', "testadmin123")
        await page1.click('button[type="submit"]')
        await page1.wait_for_url("http://localhost:8001/**")
        print("[OK] Tab 1 logged in")

        # Navigate both to bandeja
        await page1.goto("http://localhost:8001/atencion/bandeja-entrada/")
        await page2.goto("http://localhost:8001/login")
        await page2.fill('input[name="username"]', "testadmin")
        await page2.fill('input[name="password"]', "testadmin123")
        await page2.click('button[type="submit"]')
        await page2.wait_for_url("http://localhost:8001/**")
        await page2.goto("http://localhost:8001/atencion/bandeja-entrada/")
        print("[OK] Tab 2 logged in and navigated")

        # Wait for SSE to establish
        print("\n[STEP 2] Waiting for SSE OPEN in both tabs (5 seconds)...")
        await asyncio.sleep(5)

        # Check SSE state
        sse1_open = await page1.evaluate("() => { try { return window.__eventStoreLog?.find(e => e.reason === 'sse_opened') !== undefined } catch(e) { return false } }")
        sse2_open = await page2.evaluate("() => { try { return window.__eventStoreLog?.find(e => e.reason === 'sse_opened') !== undefined } catch(e) { return false } }")
        print(f"[TAB1] SSE open: {sse1_open}")
        print(f"[TAB2] SSE open: {sse2_open}")

        # Get cursor for both
        cursor1 = await page1.evaluate("() => { return JSON.stringify(window.__eventStoreLog || []).substring(0, 100) }")
        cursor2 = await page2.evaluate("() => { return JSON.stringify(window.__eventStoreLog || []).substring(0, 100) }")
        print(f"[TAB1] cursor/log: {cursor1}")
        print(f"[TAB2] cursor/log: {cursor2}")

        # NOW publish event (after SSE is open)
        print("\n[STEP 3] Publishing TEST-TIMING-001 event...")
        result = subprocess.run([
            "docker-compose", "exec", "-T", "django", "python", "manage.py", "shell"
        ], input="""
from apps.whatsapp.redis_events import get_event_bus
import time

bus = get_event_bus()
cursor_before = bus.get_latest_id()
print(f"Cursor before: {cursor_before}")

event = bus.publish("message.created", {
    "conversation_id": 2,
    "channel_id": 2,
    "cliente_id": 3,
    "message_id": 999,
    "meta_message_id": "TEST-TIMING-001",
    "sender_type": "customer",
    "preview": "TEST-TIMING-001",
    "timestamp": time.time(),
    "conversation": {
        "summary": "TEST-TIMING-001",
        "last_activity": time.time(),
        "unread_delta": 1,
        "attention_state": "bot",
        "bot_paused": False
    }
})
print(f"Event published: {event.id if event else 'None'}")
""", capture_output=True, text=True, timeout=30
        )
        print(f"[PUBLISH] Output: {result.stdout}")
        if result.stderr:
            print(f"[PUBLISH] Errors: {result.stderr[-200:]}")

        # Wait for event to arrive
        print("\n[STEP 4] Waiting 3 seconds for event propagation...")
        await asyncio.sleep(3)

        # Check if both tabs received the event
        events1 = await page1.evaluate("() => { try { return window.__eventStore?.events?.filter(e => e.data?.meta_message_id === 'TEST-TIMING-001').length || 0 } catch(e) { return -1 } }")
        events2 = await page2.evaluate("() => { try { return window.__eventStore?.events?.filter(e => e.data?.meta_message_id === 'TEST-TIMING-001').length || 0 } catch(e) { return -1 } }")

        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)
        print(f"Tab 1 TEST-TIMING-001: {events1 > 0 if events1 >= 0 else 'ERROR'} ({events1})")
        print(f"Tab 2 TEST-TIMING-001: {events2 > 0 if events2 >= 0 else 'ERROR'} ({events2})")

        if events1 > 0 and events2 > 0:
            print("\n✓ SUCCESS: Event received in both tabs!")
        else:
            print("\n✗ FAIL: Event not received")

        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
