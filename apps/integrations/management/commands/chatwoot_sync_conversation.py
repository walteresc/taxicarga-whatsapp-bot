from django.core.management.base import BaseCommand, CommandError

from apps.integrations.providers.chatwoot.exceptions import ChatwootError
from apps.integrations.services.chatwoot_projection import sync_chatwoot_conversation
from apps.whatsapp.models import ConversacionWhatsApp


class Command(BaseCommand):
    help = "Proyecta una conversación Django controlada hacia Chatwoot Sandbox."

    def add_arguments(self, parser):
        parser.add_argument("conversation_id", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            result = sync_chatwoot_conversation(options["conversation_id"], dry_run=options["dry_run"])
        except ConversacionWhatsApp.DoesNotExist as exc:
            raise CommandError("Django conversation was not found.") from exc
        except ChatwootError as exc:
            raise CommandError(f"Chatwoot sync failed: {exc}") from exc
        if result.dry_run:
            self.stdout.write("DRY RUN")
            self.stdout.write(f"CONTACT planned django_id={result.django_contact_id}")
            self.stdout.write(f"CONVERSATION planned django_id={result.django_conversation_id}")
            self.stdout.write(
                f"MESSAGES planned={result.total} incoming={result.incoming} outgoing={result.outgoing} "
                "posts=0 db_changes=0"
            )
            return
        action = lambda created: "created" if created else "reused"
        self.stdout.write("CHATWOOT SYNC OK")
        self.stdout.write(f"CONTACT action={action(result.contact_created)} django_id={result.django_contact_id} chatwoot_id={result.chatwoot_contact_id}")
        self.stdout.write(f"source_id={result.source_id}")
        self.stdout.write(f"CONVERSATION action={action(result.conversation_created)} django_id={result.django_conversation_id} chatwoot_id={result.chatwoot_conversation_id}")
        self.stdout.write(
            f"MESSAGES total={result.total} incoming={result.incoming} outgoing={result.outgoing} "
            f"created={result.messages_created} reused={result.messages_reused} failed={result.messages_failed}"
        )
        if result.failure:
            raise CommandError(f"Partial Chatwoot sync: {result.failure}")
