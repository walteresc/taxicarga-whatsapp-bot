from django.core.management.base import BaseCommand

from apps.integrations.models import IntegrationOutboxEvent


class Command(BaseCommand):
    help = "List sanitized outbox metadata."

    def add_arguments(self, parser):
        parser.add_argument("--channel-id", type=int)
        parser.add_argument("--status")
        parser.add_argument("--destination")
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        queryset = IntegrationOutboxEvent.objects.select_related("conversation").order_by("-created_at")
        if options["channel_id"]:
            queryset = queryset.filter(conversation__channel_id=options["channel_id"])
        if options["status"]:
            queryset = queryset.filter(status=options["status"])
        if options["destination"]:
            queryset = queryset.filter(destination=options["destination"])
        for event in queryset[:max(1, min(options["limit"], 200))]:
            self.stdout.write(f"id={event.id} channel={event.conversation.channel_id} destination={event.destination} status={event.status} event_type={event.event_type}")
