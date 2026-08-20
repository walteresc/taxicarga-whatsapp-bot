"""
Phase E: Analyze pending multimedia using IA.

Execute via:
  python manage.py analyze_pending_multimedia

Or schedule with cron:
  */10 * * * * cd /path && python manage.py analyze_pending_multimedia
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.whatsapp.models import MensajeAdjunto
from apps.whatsapp.ia_services import analyze_mensaje_adjunto

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Analyze pending multimedia (images) using IA"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be analyzed without doing it",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum number of items to analyze (default: 10)",
        )

    def handle(self, *args, dry_run=False, limit=10, **options):
        self.stdout.write("Starting IA analysis task...")

        # Query unanalyzed adjuntos
        unanalyzed = MensajeAdjunto.objects.filter(
            formato=MensajeAdjunto.FORMATO_IMAGEN,
            ia_analysis_result__exact="{}",  # Empty dict
            mensaje__adjuntos__isnull=False,
        ).select_related("mensaje__conversacion__cliente")[:limit]

        count = unanalyzed.count()

        if not count:
            self.stdout.write(self.style.SUCCESS("No pending analysis found."))
            return

        self.stdout.write(f"Found {count} items to analyze...")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No actual analysis"))
            for adjunto in unanalyzed:
                self.stdout.write(
                    f"  - {adjunto.filename} (adjunto_id={adjunto.id}, "
                    f"size={adjunto.file_size / 1024:.1f}KB)"
                )
            return

        # Process analysis
        success_count = 0
        fail_count = 0

        for adjunto in unanalyzed:
            try:
                result = analyze_mensaje_adjunto(adjunto.id)

                if result["success"]:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✓ {adjunto.filename}: "
                            f"{result.get('duration_ms', 0):.0f}ms"
                        )
                    )
                else:
                    fail_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ✗ {adjunto.filename}: {result.get('error', 'unknown')}"
                        )
                    )

            except Exception as e:
                fail_count += 1
                logger.exception(f"Error analyzing adjunto {adjunto.id}")
                self.stdout.write(
                    self.style.ERROR(f"  ✗ {adjunto.filename}: {str(e)}")
                )

        # Summary
        total = success_count + fail_count
        self.stdout.write(
            self.style.SUCCESS(
                f"\nAnalysis complete: {success_count}/{total} successful, "
                f"{fail_count} failed"
            )
        )
