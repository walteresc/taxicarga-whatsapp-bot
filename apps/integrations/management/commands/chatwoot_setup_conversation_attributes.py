from django.core.management.base import BaseCommand, CommandError

from apps.integrations.providers.chatwoot.client import ChatwootClient
from apps.integrations.providers.chatwoot.exceptions import ChatwootError
from apps.integrations.services.conversation_data import ATTRIBUTE_DEFINITIONS


class Command(BaseCommand):
    help = "Crea o reutiliza atributos operativos de conversacion en Chatwoot."

    def handle(self, *args, **options):
        created = reused = 0
        try:
            client = ChatwootClient()
            for key, display_name in ATTRIBUTE_DEFINITIONS.items():
                _definition, was_created = client.ensure_conversation_text_attribute(
                    key=key, display_name=display_name
                )
                created += int(was_created)
                reused += int(not was_created)
        except ChatwootError as exc:
            raise CommandError(f"Chatwoot attribute setup failed: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"created={created} reused={reused}"))
