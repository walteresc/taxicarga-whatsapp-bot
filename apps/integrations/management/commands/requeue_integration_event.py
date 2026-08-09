import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.services.inbox_outbox import requeue_dead_letter, requeue_inbox_dead_letter


class Command(BaseCommand):
    help = "Requeue exactly one dead-letter event by UUID."

    def add_arguments(self, parser):
        parser.add_argument("event_id")
        parser.add_argument("--kind", choices=["inbox", "outbox"], required=True)

    def handle(self, *args, **options):
        try:
            event_id = uuid.UUID(options["event_id"])
        except ValueError as exc:
            raise CommandError("event_id must be a UUID") from exc
        updated = requeue_inbox_dead_letter(event_id) if options["kind"] == "inbox" else requeue_dead_letter(event_id)
        if updated != 1:
            raise CommandError("One matching dead-letter event was not found.")
        self.stdout.write(self.style.SUCCESS(f"requeued {options['kind']} event={event_id}"))
