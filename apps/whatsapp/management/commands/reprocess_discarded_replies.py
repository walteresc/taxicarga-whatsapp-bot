"""Reprocess YCloud webhook events discarded because they were missing 'from'.

These are typically WhatsApp reply/quote messages where YCloud omits the customer's
phone number and only provides an opaque fromUserId + a reference to the quoted
message. Since the identity-resolution fallback chain (reply-context lookup, then
fromUserId cache) was added to YCloudMessageProcessor, some of these can now be
resolved and replayed through the normal pipeline.

Default mode is a DRY RUN: it only reports how many discarded events would now be
resolvable and by which fallback. Use --execute to actually replay them (idempotent —
existing messages are matched by meta_message_id and not duplicated).
"""
from django.core.management.base import BaseCommand

from apps.whatsapp_bot_v4.models import WebhookEvent
from apps.whatsapp_bot_v4.services.ycloud_webhook_service import (
    _normalize_ycloud_payload,
    _resolve_channel_from_payload,
)
from apps.whatsapp.services_ycloud import process_ycloud_event, _processor

DISCARD_REASONS = (
    "Inbound missing 'from' and 'phone'",
    "Inbound missing 'from'; reply-context and from_user_id fallback failed",
)


class Command(BaseCommand):
    help = "Reprocess YCloud events discarded for missing 'from' (reply/quote messages)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually replay resolvable events (default is dry-run/count only)",
        )

    def handle(self, *args, **options):
        execute = options["execute"]

        events = WebhookEvent.objects.filter(
            source="ycloud",
            discard_reason__in=DISCARD_REASONS,
        ).order_by("processed_at")

        total = events.count()
        self.stdout.write(f"Discarded events found (missing 'from'): {total}")

        resolvable_context = []
        resolvable_user_id = []
        unresolvable = []

        for evt in events:
            payload = evt.discard_payload
            if not isinstance(payload, dict):
                unresolvable.append(evt.external_message_id)
                continue

            canonical = _normalize_ycloud_payload(evt.event_type, payload)
            if not canonical:
                unresolvable.append(evt.external_message_id)
                continue

            if canonical.get("from"):
                # Already has 'from' after re-normalization (fixed from_name/context
                # extraction may have exposed it) — would resolve via normal path.
                resolvable_context.append((evt, canonical))
                continue

            cliente = _processor._resolve_cliente_by_reply_context(canonical)
            via = "reply_context"
            if not cliente:
                cliente = _processor._resolve_cliente_by_from_user_id(canonical)
                via = "from_user_id"

            if cliente:
                if via == "reply_context":
                    resolvable_context.append((evt, canonical))
                else:
                    resolvable_user_id.append((evt, canonical))
            else:
                unresolvable.append(evt.external_message_id)

        self.stdout.write(self.style.SUCCESS(
            f"Resolvable via reply-context: {len(resolvable_context)}"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"Resolvable via from_user_id cache: {len(resolvable_user_id)}"
        ))
        self.stdout.write(self.style.WARNING(
            f"Still unresolvable: {len(unresolvable)}"
        ))
        if unresolvable:
            self.stdout.write(f"  event_ids: {unresolvable[:20]}")

        if not execute:
            self.stdout.write(self.style.WARNING(
                "\nDRY RUN — no changes made. Pass --execute to replay resolvable events."
            ))
            return

        replayed = 0
        failed = 0
        for evt, canonical in resolvable_context + resolvable_user_id:
            channel = _resolve_channel_from_payload(evt.event_type, canonical, evt.discard_payload)
            if not channel:
                failed += 1
                continue
            result = process_ycloud_event(
                evt.event_type, canonical, channel, event_id=evt.external_message_id
            )
            if result.get("message"):
                replayed += 1
            else:
                failed += 1

        self.stdout.write(self.style.SUCCESS(f"Replayed: {replayed}, failed: {failed}"))
