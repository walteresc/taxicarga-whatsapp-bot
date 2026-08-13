from django.core.management.base import BaseCommand
from django.db import connection
from decouple import config
from apps.clientes.models import Cliente
from apps.whatsapp.models import WhatsAppChannel
from apps.integrations.models import ChannelIntegrationPolicy, IntegrationOutboxEvent, BotGeneration, WorkerHeartbeat
from apps.leads.models import Lead
from apps.whatsapp.models import ConversacionWhatsApp


class Command(BaseCommand):
    help = "Physical test preflight verification. Returns PASS or FAIL."

    def handle(self, *args, **options):
        results = {}

        # 1. DATABASE
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            results['DATABASE'] = 'PASS'
        except Exception as e:
            results['DATABASE'] = f'FAIL: {str(e)[:50]}'

        # 2. TEST CLIENT (ending in 320)
        test_clients = Cliente.objects.filter(telefono__endswith='320')
        results['TEST_CLIENT'] = 'PASS' if test_clients.exists() else 'FAIL'
        if test_clients.exists():
            client = test_clients.first()
            results['TEST_CLIENT_NUMBER'] = client.telefono

        # 3. CHANNEL 7 CONFIG
        try:
            ch7 = WhatsAppChannel.objects.get(id=7)
            if not ch7.activo:
                results['CHANNEL_7_ACTIVE'] = 'FAIL'
            else:
                results['CHANNEL_7_ACTIVE'] = 'PASS'

            policy = ChannelIntegrationPolicy.objects.get(channel=ch7)
            results['CHANNEL_7_INTEGRATION_ENABLED'] = 'PASS' if policy.enabled else 'FAIL'
            results['CHANNEL_7_AI_V31_MODE'] = 'PASS' if policy.ai_v31_mode == 'active' else f'FAIL: {policy.ai_v31_mode}'
        except Exception as e:
            results['CHANNEL_7'] = f'FAIL: {str(e)[:50]}'

        # 4. PENDING EVENTS
        pending_internal = IntegrationOutboxEvent.objects.filter(destination="internal", status="pending").count()
        pending_meta = IntegrationOutboxEvent.objects.filter(destination="meta_whatsapp", status="pending").count()
        results['PENDING_EVENTS_INTERNAL'] = 'PASS' if pending_internal == 0 else f'FAIL: {pending_internal}'
        results['PENDING_EVENTS_META'] = 'PASS' if pending_meta == 0 else f'FAIL: {pending_meta}'

        # 5. PENDING GENERATIONS
        pending_gens = BotGeneration.objects.filter(status="generating").count()
        results['PENDING_GENERATIONS'] = 'PASS' if pending_gens == 0 else f'FAIL: {pending_gens}'

        # 6. WORKER HEARTBEAT
        try:
            hb = WorkerHeartbeat.objects.filter(name='integration').first()
            if hb and hb.last_seen_at:
                from django.utils import timezone
                from datetime import timedelta
                now = timezone.now()
                if (now - hb.last_seen_at).total_seconds() < 60:
                    results['WORKER_HEARTBEAT'] = 'PASS'
                else:
                    results['WORKER_HEARTBEAT'] = f'STALE: {(now - hb.last_seen_at).total_seconds()}s ago'
            else:
                results['WORKER_HEARTBEAT'] = 'NOT_INITIALIZED'
        except Exception as e:
            results['WORKER_HEARTBEAT'] = f'FAIL: {str(e)[:50]}'

        # 7. OPENAI CONFIG
        key = config("OPENAI_API_KEY", default="")
        model = config("OPENAI_MODEL", default="gpt-4.1-mini")
        results['OPENAI_API_KEY'] = 'PASS' if len(key) > 20 else 'FAIL'
        results['OPENAI_MODEL'] = f'PASS: {model}'

        # 8. VERIFY TOKEN
        verify_token = config("WHATSAPP_VERIFY_TOKEN", default="")
        results['WHATSAPP_VERIFY_TOKEN'] = 'PASS' if verify_token else 'FAIL'

        # SUMMARY
        self.stdout.write("\n" + "="*70)
        self.stdout.write("PREFLIGHT VERIFICATION RESULTS")
        self.stdout.write("="*70 + "\n")

        passes = sum(1 for v in results.values() if v == 'PASS')
        failures = sum(1 for v in results.values() if 'FAIL' in str(v))
        total = passes + failures

        for key, value in sorted(results.items()):
            status = "[OK]" if value == 'PASS' else "[!!]" if 'FAIL' in str(value) else "[~]"
            self.stdout.write(f"{status} {key}: {value}")

        self.stdout.write("\n" + "="*70)
        self.stdout.write(f"RESULT: {passes}/{total} critical checks PASS")
        self.stdout.write("="*70 + "\n")

        if passes == total:
            self.stdout.write(self.style.SUCCESS("PREFLIGHT: READY FOR PHYSICAL TEST"))
        else:
            self.stdout.write(self.style.ERROR("PREFLIGHT: FAILURES DETECTED"))
