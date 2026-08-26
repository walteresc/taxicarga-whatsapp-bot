"""PASO 1: Rastrear correlation_id a través de EventStore → processEvent."""
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
    "content": "CORRELATION-TEST",
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
        "preview": "CORRELATION-TEST",
        "timestamp": msg.fecha_mensaje.isoformat(),
        "unread_delta": 1,
        "correlation_id": "{correlation_id}"
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


async def test():
    """PASO 1: Trace complete correlation_id path."""
    print("\n" + "="*80)
    print("PASO 1: CORRELATION_ID TRACE")
    print("="*80)

    sessionid = await http_login()
    corr_id = f"paso1-{uuid.uuid4().hex[:8]}"
    print(f"[OK] Correlation ID: {corr_id}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await ctx.new_page()

        # Instrument to trace correlation_id
        await page.add_init_script(f"""
        window.__trace = {{
          correlation_id: "{corr_id}",
          checkpoints: []
        }};

        function checkpoint(name, data) {{
          const entry = {{
            checkpoint: name,
            timestamp: Date.now(),
            data: data
          }};
          window.__trace.checkpoints.push(entry);
          console.log('[TRACE ' + name + '] ' + JSON.stringify(data).substring(0, 100));
        }}

        // Hook handleSSEEvent
        const origConsoleLog = console.log;
        let sseEventHooked = false;

        const checkHook = setInterval(() => {{
          try {{
            // Try to hook EventSource if eventStore is available
            if (window.__eventSourceDiagnostics && !sseEventHooked) {{
              checkpoint('ES_LISTENER_READY', {{ listeners: window.__eventSourceDiagnostics.listeners?.length || 0 }});
              sseEventHooked = true;
            }}
          }} catch(e) {{}}
        }}, 500);

        setTimeout(() => clearInterval(checkHook), 15000);

        // Capture processEvent calls via console
        console.log = function(...args) {{
          const msg = args.join(' ');
          if (msg.includes('[REALTIME processEvent]')) {{
            checkpoint('PROCESS_EVENT', {{ msg: msg.substring(0, 150) }});
          }} else if (msg.includes('{corr_id}')) {{
            checkpoint('CORRELATION_FOUND', {{ msg: msg }});
          }}
          return origConsoleLog.apply(console, args);
        }};
        """)

        # Navigate
        await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        await asyncio.sleep(2)
        print("[OK] Dashboard loaded")

        # Get cursor
        c1 = await page.evaluate("""
        async () => {
          const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
          const data = await resp.json();
          return data.snapshot_cursor;
        }
        """)
        print(f"[OK] Cursor: {c1}")

        await asyncio.sleep(1)

        # Publish
        print("[STEP] Publishing event...")
        e1_id = await publish_event(corr_id)
        print(f"[OK] Event ID: {e1_id}")

        # Wait for processing
        print("[STEP] Waiting for event processing (10s)...")
        await asyncio.sleep(5)

        # Get trace
        trace = await page.evaluate("() => window.__trace")

        print("\n" + "="*80)
        print("TRACE RESULTS")
        print("="*80)
        print(f"Correlation ID: {trace['correlation_id']}")
        print(f"Checkpoints reached: {len(trace['checkpoints'])}")

        for cp in trace['checkpoints']:
            print(f"\n  [{cp['checkpoint']}]")
            print(f"    Data: {cp['data']}")

        # Last checkpoint reached
        if trace['checkpoints']:
            last = trace['checkpoints'][-1]
            print(f"\n[LAST CHECKPOINT] {last['checkpoint']}")
        else:
            print(f"\n[NO CHECKPOINTS] Event did not reach instrumented code")

        await ctx.close()
        await browser.close()


if __name__ == '__main__':
    asyncio.run(test())
