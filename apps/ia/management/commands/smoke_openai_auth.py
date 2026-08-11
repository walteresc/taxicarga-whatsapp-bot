from django.core.management.base import BaseCommand, CommandError

from apps.ia.providers import build_provider


class Command(BaseCommand):
    help = "Hace una llamada mínima OpenAI y reporta auth sin exponer secretos."

    def handle(self, *args, **options):
        provider = build_provider("extraction", provider_name="openai")
        try:
            result = provider.generate([
                {"role": "user", "content": "Reply with exactly: OK"},
            ])
        except Exception as exc:
            status = getattr(exc, "status_code", None) or "FAIL"
            code = ((getattr(exc, "body", None) or {}).get("error") or {}).get("code")
            raise CommandError(
                f"OPENAI_AUTH=FAIL HTTP={status} ERROR_CODE={code or type(exc).__name__}"
            ) from None
        total = (result.input_tokens or 0) + (result.output_tokens or 0)
        self.stdout.write(self.style.SUCCESS(
            f"OPENAI_AUTH=OK HTTP=200 MODEL={result.model} TOKENS={total}"
        ))
