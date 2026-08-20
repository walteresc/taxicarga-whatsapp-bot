"""
Phase C: Cleanup expired multimedia files according to retention policies.

Execute via:
  python manage.py cleanup_expired_multimedia

Or schedule with cron (daily):
  0 2 * * * cd /path/to/project && python manage.py cleanup_expired_multimedia --dry-run > /var/log/cleanup.log 2>&1
  0 3 * * * cd /path/to/project && python manage.py cleanup_expired_multimedia

Note: Always run with --dry-run first to verify what will be deleted!
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.whatsapp.models import MensajeAdjunto

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Cleanup expired multimedia files according to retention policies"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually doing it (ALWAYS RUN THIS FIRST)",
        )
        parser.add_argument(
            "--keep-days",
            type=int,
            default=0,
            help="Keep files for additional N days before cleanup (safety buffer)",
        )

    def handle(self, *args, dry_run=False, keep_days=0, **options):
        self.stdout.write("Starting multimedia cleanup task...")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No files will be deleted"))
        else:
            self.stdout.write(self.style.WARNING("PRODUCTION MODE - Files WILL be deleted"))

        now = timezone.now()
        cutoff = now - timedelta(days=keep_days)

        # Find expired attachments
        expired = MensajeAdjunto.objects.filter(
            retain_until__lte=cutoff,
            protected_from_cleanup=False,
        ).select_related("mensaje__conversacion__cliente")

        count = expired.count()
        self.stdout.write(f"Found {count} expired attachments eligible for cleanup")

        if not count:
            self.stdout.write(self.style.SUCCESS("No cleanup needed."))
            return

        # Group by retention policy for reporting
        by_policy = {}
        total_size = 0

        for adjunto in expired:
            policy = adjunto.retention_policy
            if policy not in by_policy:
                by_policy[policy] = {"count": 0, "size": 0, "items": []}
            by_policy[policy]["count"] += 1
            by_policy[policy]["size"] += adjunto.file_size or 0
            by_policy[policy]["items"].append(adjunto)
            total_size += adjunto.file_size or 0

        # Report by policy
        self.stdout.write("\nBreakdown by retention policy:")
        for policy, info in sorted(by_policy.items()):
            size_mb = info["size"] / (1024 * 1024)
            self.stdout.write(
                f"  {policy}: {info['count']} files ({size_mb:.1f} MB)"
            )

        self.stdout.write(f"\nTotal: {count} files ({total_size / (1024 * 1024):.1f} MB)")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nShowing first 10 items to be deleted:"))
            for adjunto in expired[:10]:
                self.stdout.write(
                    f"  - {adjunto.filename} "
                    f"(expired: {adjunto.retain_until}, "
                    f"size: {adjunto.file_size / 1024:.1f} KB)"
                )
            if count > 10:
                self.stdout.write(f"  ... and {count - 10} more")
            return

        # Production mode: actually delete
        self.stdout.write(self.style.WARNING("\nProceeding with deletion..."))

        deleted_count = 0
        failed_count = 0

        for adjunto in expired:
            try:
                # Delete file from storage
                if adjunto.archivo:
                    try:
                        adjunto.archivo.delete(save=False)
                        logger.info(f"Deleted file: {adjunto.archivo.name}")
                    except Exception as e:
                        logger.warning(f"Could not delete file {adjunto.archivo.name}: {str(e)}")
                        failed_count += 1
                        continue

                # Delete database record
                ycloud_id = adjunto.ycloud_media_id
                adjunto.delete()
                deleted_count += 1
                logger.info(f"Deleted adjunto record: {ycloud_id}")

            except Exception as e:
                failed_count += 1
                logger.exception(f"Error deleting adjunto {adjunto.id}: {str(e)}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCleanup complete: {deleted_count} deleted, {failed_count} failed"
            )
        )

        if failed_count > 0:
            logger.warning(f"Cleanup had {failed_count} failures - review logs")
