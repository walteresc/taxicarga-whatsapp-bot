"""FASE 5B: Complete correlation trace with independent probe."""
import asyncio
import json
import subprocess
import time
import uuid
from datetime import datetime
from playwright.async_api import async_playwright
import requests


async def http_login():
    """Step 1: Login to get sessionid."""
    session = requests.Session()
    resp = session.post(
        'http://localhost:8001/dashboard/api/auth/login/',
        json={'username': 'e2e_test', 'password': 'e2e_test_password'}
    )
    if resp.status_code == 200:
        return session.cookies.get_dict().get('sessionid')
    return None


async def get_canonical_event():
    """Build canonical event from real MensajeWhatsApp 117."""
    cmd = [
        'docker', 'exec', 'taxicarga-api',
        'python', 'manage.py', 'shell', '-c',
        '''
import os, json, uuid
from datetime import datetime
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_e2e"
import django
django.setup()

from apps.whatsapp.models import MensajeWhatsApp
from apps.whatsapp.redis_events import get_event_bus

msg = MensajeWhatsApp.objects.get(id=117)
correlation_id = f"trace-{uuid.uuid4().hex[:8]}"

event_data = {
    "conversation_id": msg.conversacion_id,
    "message_id": msg.id,
    "channel_id": msg.conversacion.channel_id,
    "cliente_id": msg.conversacion.cliente_id,
    "content": msg.contenido[:50],
    "sender_type": msg.sender_type,
    "direccion": msg.direccion,
    "source": msg.origen,
    "fecha_mensaje": msg.fecha_mensaje.isoformat(),
    "unread_delta": 1,
    "correlation_id": correlation_id
}

bus = get_event_bus()
event = bus.publish("message.created", event_data)

print(f"EVENT_ID:{event.id}")
print(f"CORRELATION_ID:{correlation_id}")
print(f"MESSAGE_ID:117")
print(f"CHANNEL_ID:{msg.conversacion.channel_id}")
'''
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    event_info = {}
    for line in result.stdout.split('\n'):
        if line.startswith('EVENT_ID:'):
            event_info['event_id'] = line.split(':')[1]
        elif line.startswith('CORRELATION_ID:'):
            event_info['correlation_id'] = line.split(':')[1]
        elif line.startswith('MESSAGE_ID:'):
            event_info['message_id'] = line.split(':')[1]
        elif line.startswith('CHANNEL_ID:'):
            event_info['channel_id'] = line.split(':')[1]

    return event_info


async def main():
    print("\n" + "="*80)
    print("FASE 5B - CORRELATION TRACE TEST")
    print("="*80)

    # Step 1: Login
    print("\n[STEP 1] Login")
    sessionid = await http_login()
    if not sessionid:
        print("FAIL: Login failed")
        return
    print(f"[OK] sessionid={sessionid[:20]}")

    # Step 2: Get canonical event info
    print("\n[STEP 2] Build canonical event")
    event_info = await get_canonical_event()
    correlation_id = event_info['correlation_id']
    event_id = event_info['event_id']
    print(f"[OK] Correlation: {correlation_id}")
    print(f"[OK] Event ID: {event_id}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            extra_http_headers={'Cookie': f'sessionid={sessionid}'}
        )
        page = await context.new_page()

        # Instrument EventSource before navigation
        print("\n[STEP 3] Inject EventSource instrumentation")
        await page.add_init_script("""
        window.__eventSourceDiagnostics = {
          instances: [],
          listeners: [],
          opens: [],
          errors: [],
          events: [],
          traces: []
        };

        window.__probeState = {
          opened: false,
          events: [],
          errors: [],
          cursor: null
        };

        window.__appState = {
          opened: false,
          events: [],
          listeners_registered: false
        };

        window.__correlationTrace = {
          event_received_at: null,
          parsed_at: null,
          store_accepted_at: null,
          dom_updated_at: null
        };

        const OriginalEventSource = window.EventSource;
        window.EventSource = function(url, config) {
          const instance_id = Math.random().toString(36).substr(2, 9);
          console.log(`[DIAG] EventSource constructor: ${url} (${instance_id})`);

          window.__eventSourceDiagnostics.instances.push({
            instance_id,
            url,
            created_at: Date.now()
          });

          const es = new OriginalEventSource(url, config);

          const origAddEventListener = es.addEventListener;
          es.addEventListener = function(type, listener, options) {
            console.log(`[DIAG] addEventListener: ${type} on ${instance_id}`);
            window.__eventSourceDiagnostics.listeners.push({
              instance_id,
              type,
              added_at: Date.now()
            });
            return origAddEventListener.call(this, type, listener, options);
          };

          es.addEventListener('open', () => {
            console.log(`[DIAG] open on ${instance_id}`);
            window.__eventSourceDiagnostics.opens.push({
              instance_id,
              opened_at: Date.now()
            });
          });

          es.addEventListener('error', (e) => {
            console.log(`[DIAG] error on ${instance_id}: readyState=${e.target.readyState}`);
            window.__eventSourceDiagnostics.errors.push({
              instance_id,
              readyState: e.target.readyState,
              error_at: Date.now()
            });
          });

          // Wrap message dispatch
          const origDispatchEvent = es.dispatchEvent;
          es.dispatchEvent = function(event) {
            if (event.type && !event.type.includes('readystatechange')) {
              console.log(`[DIAG] dispatch: ${event.type} on ${instance_id}`);
              window.__eventSourceDiagnostics.events.push({
                instance_id,
                type: event.type,
                lastEventId: event.lastEventId,
                data_sample: (event.data || '').substring(0, 100),
                dispatched_at: Date.now()
              });
            }
            return origDispatchEvent.call(this, event);
          };

          return es;
        };
        window.EventSource.prototype = OriginalEventSource.prototype;
        console.log('[DIAG] EventSource instrumented');
        """)
        print("[OK] Instrumentation and states initialized")

        # Navigate to dashboard
        print("\n[STEP 5] Navigate to dashboard")
        await page.goto('http://localhost:8001/dashboard/', wait_until='domcontentloaded')
        print("[OK] Dashboard loaded")
        await asyncio.sleep(2)

        # Get snapshot cursor
        print("\n[STEP 6] Get snapshot cursor")
        cursor = await page.evaluate("""
        async () => {
          try {
            const resp = await fetch('/dashboard/whatsapp/conversaciones/api/active/');
            const data = await resp.json();
            return data.snapshot_cursor;
          } catch (e) {
            console.error('Snapshot failed:', e);
            return null;
          }
        }
        """)
        print(f"[OK] Cursor: {cursor}")

        # Step 4: Create diagnostic states (already done in init_script)
        print("\n[STEP 4] States already initialized in init_script")

        # Step 7: Create independent probe
        print("\n[STEP 7] Create independent probe EventSource")
        await page.evaluate(f"""
        () => {{
          window.__probeState.cursor = "{cursor}";
          const url = `/dashboard/whatsapp/api/events/stream/?cursor=${{encodeURIComponent("{cursor}")}}`;
          console.log('[PROBE] Opening: ' + url);

          const probe = new EventSource(url, {{ withCredentials: true }});

          probe.addEventListener('open', () => {{
            window.__probeState.opened = true;
            console.log('[PROBE] OPEN');
          }});

          probe.addEventListener('message.created', (e) => {{
            const data = JSON.parse(e.data);
            window.__probeState.events.push({{
              id: e.lastEventId,
              type: 'message.created',
              correlation_id: data.correlation_id,
              received_at: Date.now()
            }});
            console.log('[PROBE] message.created received: ' + data.correlation_id);
          }});

          probe.addEventListener('error', (e) => {{
            window.__probeState.errors.push({{
              readyState: probe.readyState,
              error_at: Date.now()
            }});
            console.log('[PROBE] ERROR: readyState=' + probe.readyState);
          }});

          window.__probe = probe;
        }}
        """)
        print("[OK] Probe created")

        # Step 8: Wait for probe OPEN
        print("\n[STEP 8] Wait for probe to open (5s)")
        for i in range(10):
            probe_open = await page.evaluate("() => window.__probeState.opened")
            if probe_open:
                print(f"[OK] Probe opened at {i}s")
                break
            await asyncio.sleep(0.5)
        else:
            print("[WARN] Probe not opened after 5s")

        # Step 9: Wait for app EventSource (should also be open)
        print("\n[STEP 9] Check app EventSource status")
        await asyncio.sleep(1)
        diag = await page.evaluate("() => window.__eventSourceDiagnostics")
        print(f"[INFO] EventSource instances: {len(diag['instances'])}")
        print(f"[INFO] Opens: {len(diag['opens'])}")
        print(f"[INFO] Listeners registered: {len(diag['listeners'])}")
        for listener in diag['listeners']:
            print(f"       - {listener['type']} on {listener['instance_id'][:8]}")

        # Step 10: Publish canonical event
        print(f"\n[STEP 10] Publish canonical event (correlation={correlation_id})")
        await asyncio.sleep(1)  # Ensure both open before publish
        print(f"[OK] Published: {event_id}")

        # Step 11: Wait for events (5 seconds)
        print("\n[STEP 11] Wait for events (5s)")
        for i in range(10):
            await asyncio.sleep(0.5)
            probe_events = await page.evaluate("() => window.__probeState.events")
            print(f"   [{i}] Probe events: {len(probe_events)}")

            if probe_events:
                for evt in probe_events:
                    if evt['correlation_id'] == correlation_id:
                        print(f"[SUCCESS] Probe received event: {evt['id']}")
                        break

        # Step 12: Gather diagnostics
        print("\n[STEP 12] Gather diagnostics")
        diag_final = await page.evaluate("() => window.__eventSourceDiagnostics")
        probe_final = await page.evaluate("() => window.__probeState")
        trace_final = await page.evaluate("() => window.__correlationTrace")

        print("\n" + "="*80)
        print("DIAGNOSTIC RESULTS")
        print("="*80)
        print(f"Probe opened: {probe_final['opened']}")
        print(f"Probe events: {len(probe_final['events'])}")
        if probe_final['events']:
            print(f"  - {probe_final['events'][0]}")

        print(f"\nEventSource instances: {len(diag_final['instances'])}")
        print(f"Opens: {len(diag_final['opens'])}")
        print(f"Listeners:")
        for listener in diag_final['listeners']:
            print(f"  - {listener['type']}")
        print(f"Events dispatched: {len(diag_final['events'])}")
        for evt in diag_final['events'][-3:]:
            print(f"  - {evt['type']}: {evt['data_sample'][:40]}")

        # RESULT
        if probe_final['events'] and any(e['correlation_id'] == correlation_id for e in probe_final['events']):
            print("\n[PASS] Probe received canonical event")
            if len(diag_final['events']) > len(diag_final['opens']):
                print("[PARTIAL] App EventSource received something")
            else:
                print("[FAIL] App EventSource did NOT receive event despite probe success")
        else:
            print("\n[FAIL] Probe did NOT receive event")

        print("\n" + "="*80)

        await context.close()
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
