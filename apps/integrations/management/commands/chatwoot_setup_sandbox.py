from django.core.management.base import BaseCommand, CommandError

from apps.integrations.providers.chatwoot.client import ChatwootClient
from apps.integrations.providers.chatwoot.exceptions import ChatwootError


class Command(BaseCommand):
    help = "Crea o reutiliza una inbox API Chatwoot sandbox."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="TaxiCarga Sandbox")

    def handle(self, *args, **options):
        try:
            inbox, created = ChatwootClient().ensure_sandbox_inbox(options["name"])
        except ChatwootError as exc:
            self.stdout.write("CHATWOOT ERROR")
            self.stdout.write(f"tipo={exc.kind}")
            self.stdout.write(f"detalle seguro={exc}")
            raise CommandError("Chatwoot sandbox setup failed.") from exc
        action = "created" if created else "reused"
        self.stdout.write(self.style.SUCCESS("CHATWOOT SANDBOX OK"))
        self.stdout.write(f"action={action}")
        self.stdout.write(f"inbox_id={inbox.get('id', '')}")
        self.stdout.write(f"inbox_name={inbox.get('name', '')}")
        self.stdout.write(f"inbox_type={inbox.get('channel_type', '')}")
