from pathlib import Path

from django.core.management.base import BaseCommand

from apps.ia.v31_artifacts import run_v31_cases
from apps.ia.v31_blind_holdout import v31_blind_holdout_cases


class Command(BaseCommand):
    help = "Ejecuta una vez el holdout ciego V3.1 congelado."

    def add_arguments(self, parser):
        parser.add_argument("--output-root",type=Path,default=Path("reports/ai_eval"))

    def handle(self, *args, **options):
        cases=v31_blind_holdout_cases()
        run_dir,summary=run_v31_cases(
            cases,options["output_root"],run_suffix="v31_blind_holdout_100")
        self.stdout.write(self.style.SUCCESS(
            f"V31_HOLDOUT={summary['schema_valid']}/100 "
            f"PASS={summary['semantic_pass']}/100 RUN={run_dir}"))
