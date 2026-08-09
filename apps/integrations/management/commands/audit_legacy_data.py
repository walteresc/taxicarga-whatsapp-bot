import json

from django.core.management.base import BaseCommand

from apps.clientes.models import Cliente, Conversacion
from apps.cotizador.models import CotizacionComercial
from apps.integrations.models import ChannelInboxMapping, IntegrationInboxEvent, IntegrationOutboxEvent
from apps.leads.models import Lead
from apps.whatsapp.models import WhatsAppChannel


class Command(BaseCommand):
    help = "Audit SQLite legacy data without exporting PII."

    def add_arguments(self, parser):
        parser.add_argument("--output")

    def handle(self, *args, **options):
        report = {
            "classification": "DUDOSO",
            "pii_exported": False,
            "counts": {
                "channels": WhatsAppChannel.objects.count(),
                "customers": Cliente.objects.count(),
                "leads": Lead.objects.count(),
                "conversations": Conversacion.objects.count(),
                "quotes": CotizacionComercial.objects.count(),
                "mappings": ChannelInboxMapping.objects.count(),
                "inbox_events": IntegrationInboxEvent.objects.count(),
                "outbox_events": IntegrationOutboxEvent.objects.count(),
            },
            "allowed_classes": ["TEST", "SEED", "DUDOSO", "CANDIDATO_REAL"],
        }
        payload = json.dumps(report, indent=2, sort_keys=True)
        if options["output"]:
            from pathlib import Path
            Path(options["output"]).write_text(payload + "\n", encoding="utf-8")
        else:
            self.stdout.write(payload)
