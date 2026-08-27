"""FASE 5B diagnostic: Redis stream identity verification.

Checks if publisher, SSE generator, and poll endpoint use identical Redis.
No manual input required — runs autonomously.
"""
import os
import sys
import json
import redis
import threading
import socket
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.whatsapp.redis_events import RedisEventBus, get_event_bus


class Command(BaseCommand):
    help = "Diagnose Redis stream configuration and identity"

    def add_arguments(self, parser):
        parser.add_argument('--publish', action='store_true', help='Publish test event')

    def handle(self, *args, **options):
        print("\n" + "="*80)
        print("FASE 5B — REDIS DIAGNOSTIC")
        print("="*80)

        # === PHASE 1: Settings ===
        print("\n[PHASE 1] Django Settings")
        print("-" * 80)
        self.check_django_settings()

        # === PHASE 2: Redis Connection ===
        print("\n[PHASE 2] Redis Connection")
        print("-" * 80)
        self.check_redis_connection()

        # === PHASE 3: Stream Inventory ===
        print("\n[PHASE 3] Stream Inventory")
        print("-" * 80)
        self.check_stream_inventory()

        # === PHASE 4: get_latest_id() behavior ===
        print("\n[PHASE 4] get_latest_id() Behavior")
        print("-" * 80)
        self.check_latest_cursor()

        # === PHASE 5: Inspect Event Structure ===
        print("\n[PHASE 5] Event Structure Analysis")
        print("-" * 80)
        self.check_event_structure()

        # === PHASE 5B: Check Active Channels ===
        print("\n[PHASE 5B] Active Channels in Database")
        print("-" * 80)
        self.check_active_channels()

        # === PHASE 5C: Check Message 117 (TEST-005) ===
        print("\n[PHASE 5C] Message 117 (TEST-005) Status")
        print("-" * 80)
        self.check_test005_message()

        # === PHASE 6: Publish Test Event ===
        if options.get('publish'):
            print("\n[PHASE 6] Publish Test Event")
            print("-" * 80)
            self.publish_test_event()

        print("\n" + "="*80)
        print("DIAGNOSTIC COMPLETE")
        print("="*80 + "\n")

    def check_django_settings(self):
        """Print effective Django settings."""
        redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
        stream_key = getattr(settings, 'WHATSAPP_EVENTS_STREAM_KEY', 'whatsapp:events')
        settings_module = os.environ.get('DJANGO_SETTINGS_MODULE', 'unknown')

        print(f"DJANGO_SETTINGS_MODULE: {settings_module}")
        print(f"REDIS_URL: {redis_url}")
        print(f"WHATSAPP_EVENTS_STREAM_KEY: {stream_key}")
        print(f"PID: {os.getpid()}")
        print(f"Thread: {threading.current_thread().name}")

    def check_redis_connection(self):
        """Test Redis connectivity."""
        redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')

        print(f"Connecting to {redis_url}...")

        try:
            r = redis.from_url(redis_url, decode_responses=True)
            r.ping()
            print("✓ Redis PING OK")

            # Get Redis INFO
            info = r.info('server')
            print(f"✓ Redis server version: {info.get('redis_version', 'unknown')}")
            print(f"✓ Redis run_id: {info.get('run_id', 'unknown')}")
            print(f"✓ Redis uptime: {info.get('uptime_in_seconds', 'unknown')}s")

            # Get current DB size
            dbsize = r.dbsize()
            print(f"✓ Current DB size: {dbsize} keys")

            return r
        except Exception as e:
            print(f"✗ Redis connection failed: {type(e).__name__}: {e}")
            return None

    def check_stream_inventory(self):
        """Check stream contents."""
        redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
        stream_key = getattr(settings, 'WHATSAPP_EVENTS_STREAM_KEY', 'whatsapp:events')

        try:
            r = redis.from_url(redis_url, decode_responses=True)

            stream_len = r.xlen(stream_key)
            print(f"Stream key: {stream_key}")
            print(f"Stream length: {stream_len}")

            if stream_len > 0:
                # Get first and last
                first_result = r.xrange(stream_key, count=1)
                last_result = r.xrevrange(stream_key, count=1)

                if first_result:
                    first_id = first_result[0][0]
                    print(f"First event ID: {first_id}")

                if last_result:
                    last_id = last_result[0][0]
                    print(f"Last event ID: {last_id}")
            else:
                print("Stream is empty")

        except Exception as e:
            print(f"✗ Error checking stream: {type(e).__name__}: {e}")

    def check_latest_cursor(self):
        """Test get_latest_id() and get_latest_cursor() against actual stream."""
        from apps.whatsapp.redis_events import get_latest_cursor

        stream_key = getattr(settings, 'WHATSAPP_EVENTS_STREAM_KEY', 'whatsapp:events')

        try:
            bus = get_event_bus()
            latest = bus.get_latest_id()
            print(f"bus.get_latest_id() returned: {repr(latest)}")

            # Test get_latest_cursor() function
            cursor = get_latest_cursor()
            print(f"get_latest_cursor() returned: {repr(cursor)}")

            # Check stream directly
            r = bus.redis
            stream_len = r.xlen(stream_key)
            print(f"Actual stream length: {stream_len}")

            if stream_len > 0:
                last_result = r.xrevrange(stream_key, count=1)
                if last_result:
                    actual_last_id = last_result[0][0]
                    print(f"Actual last event ID: {actual_last_id}")

                    if latest == actual_last_id:
                        print("✓ get_latest_id() matches actual stream")
                    else:
                        print(f"✗ MISMATCH: get_latest_id()={latest} vs actual={actual_last_id}")

                    if cursor == actual_last_id:
                        print("✓ get_latest_cursor() matches actual stream")
                    else:
                        print(f"✗ MISMATCH: get_latest_cursor()={cursor} vs actual={actual_last_id}")
            else:
                print("Stream empty, latest should be '0'")

        except Exception as e:
            print(f"✗ Error: {type(e).__name__}: {e}")

    def publish_test_event(self):
        """Publish single test event."""
        try:
            bus = get_event_bus()
            event = bus.publish(
                event_type='diagnostic.test',
                data={'message': 'FASE 5B diagnostic test', 'timestamp': str(__import__('datetime').datetime.utcnow())}
            )
            print(f"✓ Published event: {event.id}")
            print(f"  Type: {event.type}")
            print(f"  Data: {event.data}")

            # Verify in stream
            r = bus.redis
            result = r.xrange(event.id, event.id)
            if result:
                print(f"✓ Event confirmed in stream")
            else:
                print(f"✗ Event NOT found in stream")

        except Exception as e:
            print(f"✗ Publish failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    def check_event_structure(self):
        """Inspect actual event data in stream."""
        stream_key = getattr(settings, 'WHATSAPP_EVENTS_STREAM_KEY', 'whatsapp:events')

        print("\n[PHASE 6] Event Structure Analysis")
        print("-" * 80)

        try:
            bus = get_event_bus()
            r = bus.redis

            # Get last 5 events
            result = r.xrevrange(stream_key, count=5)

            if not result:
                print("No events in stream")
                return

            print(f"Last 5 events:")
            for event_id, event_data in reversed(result):
                print(f"\nEvent ID: {event_id}")
                print(f"Raw data: {event_data}")

                # Parse data
                if 'data' in event_data:
                    import json
                    try:
                        data = json.loads(event_data['data'])
                        print(f"Parsed data: {data}")

                        # Check for channel_id
                        channel_id = data.get('channel_id')
                        if channel_id:
                            print(f"✓ Has channel_id: {channel_id}")
                        else:
                            print(f"✗ Missing channel_id — will be filtered by SSE")

                    except json.JSONDecodeError as e:
                        print(f"✗ Failed to parse JSON: {e}")

        except Exception as e:
            print(f"✗ Error: {type(e).__name__}: {e}")

    def check_active_channels(self):
        """Check active WhatsApp channels in DB."""
        try:
            from apps.whatsapp.models import WhatsAppChannel

            channels = WhatsAppChannel.objects.filter(activo=True)
            print(f"Active channels: {channels.count()}")

            for ch in channels:
                print(f"  ID={ch.id}, phone_number_id={ch.phone_number_id}, activo={ch.activo}")

            if channels.count() == 0:
                print("  ✗ NO ACTIVE CHANNELS — SSE will filter out ALL events")

        except Exception as e:
            print(f"✗ Error: {type(e).__name__}: {e}")

    def check_test005_message(self):
        """Check if TEST-005 message (ID 117) exists and can be published."""
        try:
            from apps.whatsapp.models import MensajeWhatsApp

            msg = MensajeWhatsApp.objects.filter(id=117).first()
            if not msg:
                print("✗ Message ID 117 NOT FOUND in DB")
                return

            print(f"✓ Message ID 117 found")
            print(f"  Content: {msg.contenido[:80]}")
            print(f"  Conversation ID: {msg.conversacion_id}")
            print(f"  Channel ID (from conversation): {msg.conversacion.channel_id}")

            # Check if channel_id is valid
            if not msg.conversacion.channel_id:
                print(f"  ✗ Channel ID is NULL or 0 — event will be filtered by SSE")
                return

            active_channel_ids = set(
                __import__('apps.whatsapp.models', fromlist=['WhatsAppChannel']).WhatsAppChannel.objects.filter(
                    activo=True
                ).values_list('id', flat=True)
            )

            if msg.conversacion.channel_id in active_channel_ids:
                print(f"  ✓ Channel {msg.conversacion.channel_id} is active")
            else:
                print(f"  ✗ Channel {msg.conversacion.channel_id} is NOT active")

        except Exception as e:
            print(f"✗ Error: {type(e).__name__}: {e}")
