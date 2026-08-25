"""FASE 5B Diagnostic: Trace event from Redis → Generator → Browser"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from datetime import datetime
from apps.whatsapp.redis_events import get_event_bus, get_events
from apps.dashboard.views_sse import _event_generator
from django.test import RequestFactory

User = get_user_model()


class Command(BaseCommand):
    help = "Diagnostic test for SSE event delivery (FASES 2-6)"

    def handle(self, *args, **options):
        print("\n" + "="*80)
        print("FASE 5B DIAGNOSTIC: Where do events get lost?")
        print("="*80 + "\n")

        # Get user
        user = User.objects.get(username='e2e_asesor')
        self.stdout.write(f"[TEST USER] {user.username} (groups: {', '.join(user.groups.values_list('name', flat=True))})")

        # PHASE 2: Publish event
        self.stdout.write("\n[PHASE 2] Publishing diagnostic event...")
        bus = get_event_bus()
        event_data = {
            "conversation_id": 2,
            "channel_id": 2,
            "cliente_id": 3,
            "message_id": 999,
            "meta_message_id": "diag_test_001",
            "sender_type": "customer",
            "preview": "FASE5B-DIAGNOSTIC-EVENT",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "conversation": {
                "summary": "FASE5B-DIAGNOSTIC",
                "last_activity": datetime.utcnow().isoformat() + "Z",
                "unread_delta": 1,
                "attention_state": "bot",
                "bot_paused": False,
            }
        }

        cursor_before = bus.get_latest_id()
        event = bus.publish("message.created", event_data)
        self.stdout.write(f"  Event published: {event.id}")
        self.stdout.write(f"  Cursor before: {cursor_before}")

        # PHASE 3: Query Redis
        self.stdout.write("\n[PHASE 3] Testing Redis bus isolation...")
        events = list(get_events(cursor=cursor_before))
        found = [e for e in events if e.id == event.id]
        if found:
            self.stdout.write(f"  [OK] Found event in Redis")
            self.stdout.write(f"      Channel ID: {found[0].data.get('channel_id')}")
            self.stdout.write(f"      Preview: {found[0].data.get('preview')}")
        else:
            self.stdout.write(f"  [FAIL] Event NOT found in Redis")

        # PHASE 4: Authorization
        self.stdout.write("\n[PHASE 4] Testing auth filter...")
        if found:
            channel_id = found[0].data.get('channel_id')
            authorized_channels = set([2])  # User sees channel 2
            is_authorized = channel_id in authorized_channels
            self.stdout.write(f"  Event channel_id: {channel_id}")
            self.stdout.write(f"  User can access: {is_authorized}")

        # PHASE 5/6: Generator
        self.stdout.write("\n[PHASE 5/6] Testing SSE generator...")
        factory = RequestFactory()
        req = factory.get('/dashboard/whatsapp/api/events/stream/')
        req.user = user

        generator = _event_generator(req, bus, cursor_before, cursor_too_old=False)

        # Consume yields
        yields_captured = 0
        event_found_in_generator = False
        try:
            for i, data in enumerate(generator):
                yields_captured += 1
                if 'DIAGNOSTIC' in data or event.id.encode() in data.encode() if isinstance(data, str) else b'DIAGNOSTIC' in data:
                    event_found_in_generator = True
                    self.stdout.write(f"  [OK] Generator yielded diagnostic event")
                    break
                if yields_captured >= 15:  # Safety limit
                    break
        except Exception as e:
            self.stdout.write(f"  [ERROR] Generator error: {str(e)[:100]}")

        # SUMMARY
        self.stdout.write("\n" + "="*80)
        self.stdout.write("DIAGNOSTIC RESULTS")
        self.stdout.write("="*80)
        self.stdout.write(f"[2] Event published to Redis: {'YES' if event else 'NO'}")
        self.stdout.write(f"[3] Redis returns event: {'YES' if found else 'NO'}")
        self.stdout.write(f"[4] Event passes auth: {'YES' if (found and is_authorized) else 'N/A'}")
        self.stdout.write(f"[5/6] Generator yields event: {'YES' if event_found_in_generator else 'NO'}")
        self.stdout.write(f"\nGenerator yields captured: {yields_captured}")

        if event and found and (found and is_authorized) and not event_found_in_generator:
            self.stdout.write(self.style.ERROR("\nBLOCKER FOUND: Event in Redis and authorized, but NOT yielded by generator!"))
            self.stdout.write(self.style.ERROR("Problem location: views_sse.py _event_generator() loop or filter"))
