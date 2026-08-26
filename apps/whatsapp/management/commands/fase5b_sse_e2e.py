"""FASE 5B E2E test: Publish → poll → verify complete chain."""
import json
import time
import threading
from django.core.management.base import BaseCommand
from apps.whatsapp.redis_events import get_event_bus, get_events, get_latest_cursor
from django.conf import settings


class Command(BaseCommand):
    help = "E2E test: publish event and verify SSE generator retrieves it"

    def handle(self, *args, **options):
        print("\n" + "="*80)
        print("FASE 5B — SSE E2E TEST")
        print("="*80)

        try:
            # Step 1: Get current latest cursor
            print("\n[STEP 1] Capture current stream state")
            print("-" * 80)
            bus = get_event_bus()
            current_latest = get_latest_cursor()
            print(f"Current latest cursor: {current_latest}")

            stream_key = getattr(settings, 'WHATSAPP_EVENTS_STREAM_KEY', 'whatsapp:events')
            current_len = bus.redis.xlen(stream_key)
            print(f"Stream length before: {current_len}")

            # Step 2: Publish test event
            print("\n[STEP 2] Publish test event")
            print("-" * 80)
            correlation_id = f"e2e-test-{int(time.time()*1000)}"
            event = bus.publish(
                event_type='message.created',
                data={
                    'conversation_id': 2,
                    'channel_id': 2,
                    'cliente_id': 3,
                    'message_id': 9999,
                    'meta_message_id': correlation_id,
                    'sender_type': 'test',
                    'direction': 'test',
                    'content_type': 'text',
                    'preview': f'E2E Test {correlation_id}',
                    'timestamp': time.time(),
                    'correlation_id': correlation_id,
                }
            )
            print(f"✓ Published event: {event.id}")
            print(f"  Correlation ID: {correlation_id}")

            # Step 3: Verify in Redis
            print("\n[STEP 3] Verify event in Redis")
            print("-" * 80)
            new_len = bus.redis.xlen(stream_key)
            print(f"Stream length after: {new_len}")
            print(f"Difference: {new_len - current_len}")

            if new_len > current_len:
                print("✓ Stream grew by at least 1 event")
            else:
                print("✗ Stream did NOT grow — publish failed!")
                return

            # Step 4: Test get_events_since() with OLD cursor
            print("\n[STEP 4] Simulate SSE polling with old cursor")
            print("-" * 80)
            print(f"Polling from cursor: {current_latest}")

            polled_events = get_events(cursor=current_latest)
            print(f"get_events() returned {len(polled_events)} events")

            if not polled_events:
                print("✗ CRITICAL: get_events() returned EMPTY when it should return new event!")
                print("  This is the SSE blocker")
                return

            # Find our test event
            found_test_event = None
            for evt in polled_events:
                if evt.data.get('correlation_id') == correlation_id:
                    found_test_event = evt
                    break

            if found_test_event:
                print(f"✓ Test event found in polled events!")
                print(f"  Event ID: {found_test_event.id}")
                print(f"  Event type: {found_test_event.type}")
                print(f"  Event data keys: {list(found_test_event.data.keys())}")
            else:
                print("✗ Test event NOT found in polled events")
                print(f"  Polled events: {[e.id for e in polled_events]}")

            # Step 5: Test authorization filter
            print("\n[STEP 5] Test authorization filter")
            print("-" * 80)
            channel_id = found_test_event.data.get('channel_id') if found_test_event else None
            print(f"Event channel_id: {channel_id}")

            if channel_id:
                active_channel_ids = set(
                    __import__('apps.whatsapp.models', fromlist=['WhatsAppChannel']).WhatsAppChannel.objects.filter(
                        activo=True
                    ).values_list('id', flat=True)
                )
                print(f"Active channels: {active_channel_ids}")

                if channel_id in active_channel_ids:
                    print(f"✓ Channel {channel_id} is authorized")
                else:
                    print(f"✗ Channel {channel_id} is NOT authorized — will be filtered")
            else:
                print("✗ Event has NO channel_id — will be filtered")

            # Step 6: Simulate full SSE generator flow
            print("\n[STEP 6] Simulate SSE generator flow")
            print("-" * 80)
            print("(This is what the actual SSE generator does)")

            from collections import deque

            last_event_id = current_latest
            print(f"Starting from cursor: {last_event_id}")

            # Initial load
            events_gen = get_events(cursor=last_event_id)
            events = list(events_gen)
            print(f"Initial load: {len(events)} events")

            # Simulate authorization check
            authorized_channel_ids = set(
                __import__('apps.whatsapp.models', fromlist=['WhatsAppChannel']).WhatsAppChannel.objects.filter(
                    activo=True
                ).values_list('id', flat=True)
            )

            def is_event_authorized(event):
                channel_id = event.data.get('channel_id')
                if not channel_id:
                    return False
                return channel_id in authorized_channel_ids

            pending = deque()
            last_yielded_id = last_event_id
            authorized_count = 0
            filtered_count = 0

            for event in events:
                if is_event_authorized(event):
                    pending.append(event)
                    last_yielded_id = event.id
                    authorized_count += 1
                    print(f"  ✓ Authorized event {event.id} ({event.type})")
                else:
                    filtered_count += 1
                    print(f"  ✗ Filtered event {event.id} (no channel_id or unauthorized)")

            print(f"Total: {authorized_count} authorized, {filtered_count} filtered")
            print(f"Pending queue: {len(pending)} events ready to send")

            if pending:
                print("\n✓ SUCCESS: Event would be sent to client")
                for evt in pending:
                    print(f"  Would send: {evt.id} ({evt.type})")
            else:
                print("\n✗ FAILURE: No events in queue — client receives NOTHING")

        except Exception as e:
            print(f"\n✗ Exception: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        print("\n" + "="*80)
        print("E2E TEST COMPLETE")
        print("="*80 + "\n")
