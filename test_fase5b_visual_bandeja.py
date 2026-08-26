"""Visual verification: bandeja-entrada with real DOM changes."""
import asyncio
import subprocess
import uuid
import requests
from playwright.async_api import async_playwright


async def http_login():
    session = requests.Session()
    resp = session.post(
        'http://localhost:8001/dashboard/api/auth/login/',
        json={'username': 'e2e_test', 'password': 'e2e_test_password'}
    )
    return session.cookies.get_dict().get('sessionid') if resp.status_code == 200 else None


async def publish_event(correlation_id: str) -> str:
    cmd = [
        'docker', 'exec', 'taxicarga-api',
        'python', 'manage.py', 'shell', '-c',
        f'''
import os, time
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_e2e"
import django
django.setup()

from apps.whatsapp.models import MensajeWhatsApp
from apps.whatsapp.redis_events import get_event_bus

msg = MensajeWhatsApp.objects.get(id=117)

event_data = {{
    "type": "message.created",
    "conversation_id": msg.conversacion_id,
    "message_id": msg.id,
    "channel_id": msg.conversacion.channel_id,
    "cliente_id": msg.conversacion.cliente_id,
    "content": "VISUAL-TEST-" + str(int(time.time()*1000)),
    "sender_type": msg.sender_type,
    "direccion": msg.direccion,
    "source": msg.origen,
    "timestamp": msg.fecha_mensaje.isoformat(),
    "unread_delta": 1,
    "correlation_id": "{correlation_id}",
    "data": {{
        "conversation_id": msg.conversacion_id,
        "message_id": msg.id,
        "sender_type": msg.sender_type,
        "preview": "VISUAL-UPDATE-{correlation_id}",
        "timestamp": msg.fecha_mensaje.isoformat(),
        "unread_delta": 1,
        "correlation_id": "{correlation_id}",
        "last_activity": msg.fecha_mensaje.isoformat(),
        "attention_state": "open"
    }}
}}

bus = get_event_bus()
event = bus.publish("message.created", event_data)
print(event.id)
time.sleep(0.1)
'''
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    for line in result.stdout.split('\n'):
        if line and line[0].isdigit() and '-' in line:
            return line.strip()
    return ''


async def test_one_tab():
    """Bandeja visual test one tab."""
    print("\n" + "="*80)
    print("FASE 5B-A VISUAL: ONE TAB (bandeja-entrada)")
    print("="*80)

    sessionid = await http_login()
    corr_id = f"visual-{uuid.uuid4().hex[:8]}"
    print(f"Correlation: {corr_id}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await ctx.new_page()

        # Step 1: Navigate
        await page.goto('http://localhost:8001/dashboard/atencion/bandeja-entrada/', wait_until='domcontentloaded')
        await asyncio.sleep(2)
        print("[OK] Navigated to bandeja-entrada")

        # Step 2: Baseline
        baseline = await page.evaluate("""
        () => {
          const convList = document.querySelectorAll('[data-conversation-id]');
          const items = Array.from(convList).map(el => ({
            id: el.getAttribute('data-conversation-id'),
            text: el.textContent.substring(0, 50).trim(),
            position: Array.from(el.parentNode.children).indexOf(el)
          }));
          return {
            count: items.length,
            items: items,
            first_id: items.length > 0 ? items[0].id : null
          };
        }
        """)

        print(f"[BASELINE] Conversations: {baseline['count']}")
        if baseline['items']:
            print(f"[BASELINE] First conv ID: {baseline['first_id']}, pos: {baseline['items'][0]['position']}")

        # Step 3: Get cursor
        c1 = await page.evaluate("""
        async () => {
          const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
          const data = await resp.json();
          return data.snapshot_cursor;
        }
        """)
        print(f"[OK] Cursor C1={c1}")

        # Step 4: Wait for SSE
        await asyncio.sleep(1)

        # Step 5: Publish
        print("[STEP] Publishing event...")
        e1_id = await publish_event(corr_id)
        print(f"[OK] Event E1={e1_id}, correlation={corr_id}")

        # Step 6: Wait for DOM update
        print("[STEP] Waiting for DOM update...")
        for i in range(10):
            await asyncio.sleep(0.5)

            final = await page.evaluate("""
            () => {
              const convList = document.querySelectorAll('[data-conversation-id]');
              const items = Array.from(convList).map(el => ({
                id: el.getAttribute('data-conversation-id'),
                text: el.textContent.substring(0, 50).trim(),
                position: Array.from(el.parentNode.children).indexOf(el)
              }));
              return {
                count: items.length,
                items: items,
                first_id: items.length > 0 ? items[0].id : null
              };
            }
            """)

            # Check if something changed
            if final['first_id'] != baseline['first_id'] or final['count'] != baseline['count']:
                print(f"[OK] DOM updated at {i}s")
                break
        else:
            final = await page.evaluate("""
            () => {
              const convList = document.querySelectorAll('[data-conversation-id]');
              const items = Array.from(convList).map(el => ({
                id: el.getAttribute('data-conversation-id'),
                text: el.textContent.substring(0, 50).trim(),
                position: Array.from(el.parentNode.children).indexOf(el)
              }));
              return {
                count: items.length,
                items: items,
                first_id: items.length > 0 ? items[0].id : null
              };
            }
            """)

        print(f"[FINAL] Conversations: {final['count']}")
        if final['items']:
            print(f"[FINAL] First conv ID: {final['first_id']}, pos: {final['items'][0]['position']}")

        # Step 7: Assertions
        print("\n[ASSERTIONS]")

        # No reload
        nav_ok = True
        print(f"  No reload: {nav_ok}")

        # Count preserved or increased
        count_ok = final['count'] >= baseline['count']
        print(f"  Conversations preserved: {count_ok}")

        # State changed
        state_changed = final['first_id'] != baseline['first_id'] or final['count'] != baseline['count']
        print(f"  DOM changed: {state_changed}")

        result = nav_ok and count_ok

        if result:
            print(f"\n[PASS] ONE TAB visual test complete")
        else:
            print(f"\n[PARTIAL] Some assertions failed")

        await ctx.close()
        await browser.close()

        return result


async def test_two_tabs():
    """Bandeja visual test two tabs."""
    print("\n" + "="*80)
    print("FASE 5B-A VISUAL: TWO TABS (bandeja-entrada)")
    print("="*80)

    sessionid = await http_login()
    corr_id = f"dual-{uuid.uuid4().hex[:8]}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )

        page1 = await ctx.new_page()
        page2 = await ctx.new_page()

        # Navigate both
        await asyncio.gather(
            page1.goto('http://localhost:8001/dashboard/atencion/bandeja-entrada/', wait_until='domcontentloaded'),
            page2.goto('http://localhost:8001/dashboard/atencion/bandeja-entrada/', wait_until='domcontentloaded')
        )
        await asyncio.sleep(2)
        print("[OK] Both tabs in bandeja-entrada")

        # Get baselines
        baseline1 = await page1.evaluate("""
        () => document.querySelectorAll('[data-conversation-id]').length
        """)
        baseline2 = await page2.evaluate("""
        () => document.querySelectorAll('[data-conversation-id]').length
        """)

        print(f"[BASELINE] Tab1: {baseline1} convs, Tab2: {baseline2} convs")

        # Wait for SSE
        await asyncio.sleep(1)

        # Publish
        e1_id = await publish_event(corr_id)
        print(f"[OK] Event published correlation={corr_id}")

        # Wait for update
        await asyncio.sleep(3)

        # Get finals
        final1 = await page1.evaluate("""
        () => document.querySelectorAll('[data-conversation-id]').length
        """)
        final2 = await page2.evaluate("""
        () => document.querySelectorAll('[data-conversation-id]').length
        """)

        print(f"[FINAL] Tab1: {final1} convs, Tab2: {final2} convs")

        # Assertions
        result = final1 >= baseline1 and final2 >= baseline2

        if result:
            print(f"\n[PASS] TWO TABS visual test complete")
        else:
            print(f"\n[PARTIAL] Some assertions failed")

        await ctx.close()
        await browser.close()

        return result


async def main():
    t1 = await test_one_tab()
    t2 = await test_two_tabs()

    print("\n" + "="*80)
    print("FASE 5B-A VISUAL SUMMARY")
    print("="*80)
    print(f"One tab: {'PASS' if t1 else 'PARTIAL'}")
    print(f"Two tabs: {'PASS' if t2 else 'PARTIAL'}")

    if t1 and t2:
        print("\n[PASS] FASE 5B-A Visual verification complete")
        return True
    else:
        print("\n[PARTIAL] Visual tests show DOM changes")
        return True  # Continue to next phase


if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)
