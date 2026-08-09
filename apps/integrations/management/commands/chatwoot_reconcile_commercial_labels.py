from django.core.management.base import BaseCommand

from apps.integrations.services.commercial_labels import (
    process_commercial_label_event, queue_commercial_label_projection,
)
from apps.whatsapp.models import ConversacionWhatsApp


class Command(BaseCommand):
    help = "Encola y opcionalmente procesa labels comerciales desde Django."

    def add_arguments(self, parser):
        parser.add_argument("--conversation-id", type=int)
        parser.add_argument("--channel-id", type=int)
        parser.add_argument("--process", action="store_true")

    def handle(self, *args, **options):
        queryset = ConversacionWhatsApp.objects.all()
        if options["conversation_id"]:
            queryset = queryset.filter(pk=options["conversation_id"])
        if options["channel_id"]:
            queryset = queryset.filter(channel_id=options["channel_id"])
        queued = processed = 0
        for conversation_id in queryset.values_list("id", flat=True).iterator():
            event, created = queue_commercial_label_projection(conversation_id)
            queued += int(created)
            if event and options["process"]:
                process_commercial_label_event(event.id, force=True)
                processed += 1
        self.stdout.write(self.style.SUCCESS(f"queued={queued} processed={processed}"))
