from django.core.management.base import BaseCommand, CommandError

from apps.integrations.providers.chatwoot.client import ChatwootClient
from apps.integrations.providers.chatwoot.exceptions import ChatwootError


class Command(BaseCommand):
    help = "Valida conectividad Django hacia el account Chatwoot configurado."

    def handle(self, *args, **options):
        try:
            account, inbox = ChatwootClient().check()
        except ChatwootError as exc:
            self.stdout.write("CHATWOOT ERROR")
            self.stdout.write(f"tipo={exc.kind}")
            self.stdout.write(f"detalle seguro={exc}")
            raise CommandError("Chatwoot check failed.") from exc
        self.stdout.write(self.style.SUCCESS("CHATWOOT OK"))
        self.stdout.write(f"account_id={account.get('id', '')}")
        self.stdout.write(f"account_name={account.get('name', '')}")
        if inbox:
            self.stdout.write(f"inbox_id={inbox.get('id', '')}")
            self.stdout.write(f"inbox_name={inbox.get('name', '')}")
