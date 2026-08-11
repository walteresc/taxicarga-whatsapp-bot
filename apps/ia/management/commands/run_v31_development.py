from pathlib import Path

from django.core.management.base import BaseCommand

from apps.ia.v31_artifacts import run_v31_cases
from apps.ia.v3_development import v3_development_cases


class Command(BaseCommand):
    help = "Ejecuta V3.1 contra V3_DEVELOPMENT_SET congelado de 100 casos."

    def add_arguments(self, parser):
        parser.add_argument("--output-root",type=Path,default=Path("reports/ai_eval"))

    def handle(self, *args, **options):
        cases=v3_development_cases()
        if len(cases) != 100:
            raise RuntimeError(f"V3_DEVELOPMENT_SET expected 100, got {len(cases)}")
        run_dir,summary=run_v31_cases(
            cases,options["output_root"],run_suffix="v31_development_100")
        self.stdout.write(self.style.SUCCESS(
            f"V31_DEVELOPMENT={summary['schema_valid']}/100 "
            f"PASS={summary['semantic_pass']}/100 RUN={run_dir}"))
