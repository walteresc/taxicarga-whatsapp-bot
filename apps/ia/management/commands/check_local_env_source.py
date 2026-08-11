from pathlib import Path

from decouple import Config, RepositoryEnv
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verifica sin imprimir secretos que Django usa OPENAI_API_KEY del .env local."

    def add_arguments(self, parser):
        parser.add_argument("--reject-value", default="")

    def handle(self, *args, **options):
        env_path = Path(settings.BASE_DIR) / ".env"
        project_key = Config(RepositoryEnv(str(env_path)))("OPENAI_API_KEY", default="")
        if not project_key:
            raise CommandError("PROJECT_ENV_OPENAI_API_KEY_ABSENT")
        if settings.OPENAI_API_KEY != project_key:
            raise CommandError("DJANGO_OPENAI_KEY_SOURCE_MISMATCH")
        if options["reject_value"] and settings.OPENAI_API_KEY == options["reject_value"]:
            raise CommandError("INHERITED_OPENAI_KEY_NOT_REMOVED")
        self.stdout.write(self.style.SUCCESS("LOCAL_OPENAI_KEY_SOURCE=PROJECT_ENV OK"))
