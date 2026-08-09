import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.providers.chatwoot.client import ChatwootClient
from apps.integrations.providers.chatwoot.exceptions import ChatwootError


WEBHOOK_NAME = "TaxiCarga Django Sandbox"
SUBSCRIPTIONS = ["message_created", "conversation_updated"]
ATTENTION_ATTRIBUTE_KEY = "taxicarga_attention_control"


def _replace_env_values(path, values):
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = original.splitlines()
    remaining = dict(values)
    result = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in remaining:
            result.append(f"{key}={remaining.pop(key)}")
        else:
            result.append(line)
    result.extend(f"{key}={value}" for key, value in remaining.items())
    content = "\n".join(result) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=".chatwoot-webhook-", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(content)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _existing_env_value(path, key):
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    return ""


def _allowed_hosts_with(path, hostname):
    configured = _existing_env_value(path, "ALLOWED_HOSTS")
    hosts = [item.strip() for item in configured.split(",") if item.strip()]
    if hostname and hostname not in hosts:
        hosts.append(hostname)
    return ",".join(hosts)


class Command(BaseCommand):
    help = "Create or reuse the signed Chatwoot sandbox webhook without exposing its secret."

    def add_arguments(self, parser):
        parser.add_argument("public_url")
        parser.add_argument("--env-file", default=".env")
        parser.add_argument("--rotate-secret", action="store_true")

    def handle(self, *args, **options):
        url = options["public_url"].rstrip("/") + "/"
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise CommandError("public_url must be an HTTP(S) URL.")
        if parsed.path != "/webhooks/chatwoot/":
            raise CommandError("public_url must target only /webhooks/chatwoot/.")
        env_path = Path(options["env_file"]).resolve()
        try:
            client = ChatwootClient()
            if options["rotate_secret"]:
                for existing in client.list_webhooks():
                    if existing.get("name") == WEBHOOK_NAME:
                        client.delete_webhook(existing["id"])
            webhook, created, updated = client.ensure_webhook(
                name=WEBHOOK_NAME,
                url=url,
                subscriptions=SUBSCRIPTIONS,
            )
            _attribute, attribute_created = client.ensure_conversation_list_attribute(
                key=ATTENTION_ATTRIBUTE_KEY,
                display_name="Control de atención",
                values=["Asesor", "Bot"],
            )
        except ChatwootError as exc:
            raise CommandError(str(exc)) from exc
        secret = str(webhook.get("secret") or "")
        existing_secret = _existing_env_value(env_path, "CHATWOOT_WEBHOOK_SECRET")
        effective_secret = secret or existing_secret
        if not effective_secret:
            raise CommandError("Webhook reused without a secret and no local secret is configured.")
        _replace_env_values(env_path, {
            "CHATWOOT_WEBHOOK_ENABLED": "true",
            "CHATWOOT_WEBHOOK_SECRET": effective_secret,
            "ALLOWED_HOSTS": _allowed_hosts_with(env_path, parsed.hostname),
        })
        action = "created" if created else "updated" if updated else "reused"
        self.stdout.write(self.style.SUCCESS(
            f"CHATWOOT WEBHOOK OK action={action} id={webhook.get('id')} "
            f"name={WEBHOOK_NAME} subscriptions=message_created,conversation_updated "
            f"attribute={'created' if attribute_created else 'reused'} secret=CONFIGURED"
        ))
