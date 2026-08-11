from pathlib import Path
from django.core.management.base import BaseCommand
from apps.ia.v31_artifacts import run_v31_cases
from apps.ia.v31_smoke import v31_smoke_cases


class Command(BaseCommand):
    help="Ejecuta exactamente diez casos V3.1 y persiste artifacts."
    def add_arguments(self,parser): parser.add_argument("--output-root",type=Path,default=Path("reports/ai_eval"))
    def handle(self,*args,**options):
        run_dir,summary=run_v31_cases(v31_smoke_cases(),options["output_root"])
        self.stdout.write(self.style.SUCCESS(
            f"V31_SMOKE={summary['schema_valid']}/10 PASS={summary['semantic_pass']}/10 RUN={run_dir}"))
