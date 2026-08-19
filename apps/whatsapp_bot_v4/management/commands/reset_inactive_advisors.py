"""Management command: Reset inactive advisor control after timeout."""

import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.whatsapp_bot_v4.models import ConversationOwnership

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reset advisor control for inactive conversations (timeout after N minutes)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout-minutes',
            type=int,
            default=15,
            help='Timeout in minutes (default: 15)'
        )

    def handle(self, *args, **options):
        timeout_minutes = options['timeout_minutes']
        cutoff_time = timezone.now() - timedelta(minutes=timeout_minutes)

        # Find conversations where advisor has been inactive beyond timeout
        updated = ConversationOwnership.objects.filter(
            owner_type=ConversationOwnership.OWNER_ADVISOR,
            control_mode=ConversationOwnership.MODE_AUTOMATIC,
            last_human_message_at__lt=cutoff_time
        ).update(owner_type=ConversationOwnership.OWNER_BOT)

        logger.info(
            "reset_inactive_advisors timeout_minutes=%d cutoff_time=%s reset_count=%d",
            timeout_minutes, cutoff_time, updated,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Reset {updated} inactive advisor controls (timeout: {timeout_minutes}min)"
            )
        )
