from pathlib import Path

from django.core.management.base import BaseCommand

from apps.ia.v31_artifacts import run_v31_cases
from apps.ia.v31_blind_holdout_round2 import v31_blind_holdout_round2_cases


class Command(BaseCommand):
    help = "Ejecuta una vez el segundo holdout ciego V3.1 congelado."

    def add_arguments(self, parser):
        parser.add_argument("--output-root",type=Path,default=Path("reports/ai_eval"))

    def handle(self, *args, **options):
        run_dir,summary=run_v31_cases(v31_blind_holdout_round2_cases(),
            options["output_root"],run_suffix="v31_blind_holdout_round2_100")
        self.stdout.write(self.style.SUCCESS(
            f"V31_HOLDOUT_R2={summary['schema_valid']}/100 "
            f"PASS={summary['semantic_pass']}/100 RUN={run_dir}"))
