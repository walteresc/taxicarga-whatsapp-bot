"""
Phase C: Download pending multimedia from YCloud.

Execute via:
  python manage.py download_pending_multimedia

Or schedule with cron:
  */5 * * * * cd /path/to/project && python manage.py download_pending_multimedia
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.whatsapp.models import MensajeWhatsApp, MensajeAdjunto
from apps.whatsapp.services import download_mensaje_adjunto

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Download pending multimedia from YCloud for MensajeWhatsApp instances"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be downloaded without actually doing it",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of files to download (default: 50)",
        )
        parser.add_argument(
            "--formato",
            type=str,
            choices=["imagen", "video", "audio", "documento"],
            help="Only download specific format (default: all)",
        )

    def handle(self, *args, dry_run=False, limit=50, formato=None, **options):
        self.stdout.write("Starting multimedia download task...")

        # Query pending media
        query = MensajeWhatsApp.objects.filter(
            media_status__in=[
                MensajeWhatsApp.MEDIA_PENDING,
                MensajeWhatsApp.MEDIA_DOWNLOADING,
            ],
            ycloud_media_id__isnull=False,
            ycloud_media_id__gt="",
        ).select_related("conversacion__cliente")

        if formato:
            query = query.filter(tipo=formato)

        pending = query[:limit]
        count = pending.count()

        if not count:
            self.stdout.write(self.style.SUCCESS("No pending media found."))
            return

        self.stdout.write(f"Found {count} pending items to download...")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No actual downloads"))
            for msg in pending:
                self.stdout.write(
                    f"  - {msg.tipo}: {msg.ycloud_media_id} "
                    f"(conversacion={msg.conversacion.id}, "
                    f"cliente={msg.conversacion.cliente.telefono})"
                )
            return

        # Process downloads
        success_count = 0
        fail_count = 0
        skip_count = 0

        for msg in pending:
            try:
                # Skip if already has adjunto
                if msg.adjuntos.exists():
                    skip_count += 1
                    self.stdout.write(
                        f"  SKIP {msg.tipo}: {msg.ycloud_media_id} (already downloaded)"
                    )
                    continue

                # Construct download URL (format depends on YCloud API)
                # TODO: Implement URL generation based on YCloud docs
                # For now, assume URL comes from event payload stored somewhere
                media_url = getattr(msg, "_media_url", None)
                if not media_url:
                    fail_count += 1
                    self.stdout.write(
                        f"  FAIL {msg.tipo}: {msg.ycloud_media_id} (no download URL stored)"
                    )
                    msg.media_status = MensajeWhatsApp.MEDIA_FAILED
                    msg.save(update_fields=["media_status"])
                    continue

                # Download
                msg.media_status = MensajeWhatsApp.MEDIA_DOWNLOADING
                msg.save(update_fields=["media_status"])

                result = download_mensaje_adjunto(
                    mensaje=msg,
                    media_url=media_url,
                    media_id=msg.ycloud_media_id,
                    formato=msg.tipo,
                    max_retries=3,
                )

                if result["success"]:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  OK {msg.tipo}: {msg.ycloud_media_id} "
                            f"({result['file_size']} bytes)"
                        )
                    )
                else:
                    fail_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"  FAIL {msg.tipo}: {msg.ycloud_media_id} - {result['reason']}"
                        )
                    )
                    msg.media_status = MensajeWhatsApp.MEDIA_FAILED
                    msg.save(update_fields=["media_status"])

            except Exception as e:
                fail_count += 1
                logger.exception(f"Error processing media {msg.ycloud_media_id}")
                self.stdout.write(
                    self.style.ERROR(f"  FAIL {msg.tipo}: {msg.ycloud_media_id} - {str(e)}")
                )

        # Summary
        total = success_count + fail_count + skip_count
        self.stdout.write(
            self.style.SUCCESS(
                f"\nSummary: {success_count} downloaded, {fail_count} failed, "
                f"{skip_count} skipped (of {total})"
            )
        )
