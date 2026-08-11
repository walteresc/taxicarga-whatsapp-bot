from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ia.v3_artifacts import run_v3_cases
from apps.ia.v3_development import v3_development_cases


class Command(BaseCommand):
    help = "Ejecuta exactamente tres casos reales V3 y persiste evidencia."

    def add_arguments(self, parser):
        parser.add_argument("--case-id", action="append", dest="case_ids")
        parser.add_argument("--output-root", type=Path, default=Path("reports/ai_eval"))

    def handle(self, *args, **options):
        ids = options["case_ids"] or ["s17", "s54", "s47"]
        if len(ids) != 3 or len(set(ids)) != 3:
            raise CommandError("Smoke V3 exige exactamente 3 case-id distintos.")
        index = {case["id"]: case for case in v3_development_cases()}
        missing = [case_id for case_id in ids if case_id not in index]
        if missing:
            raise CommandError(f"Casos inexistentes: {', '.join(missing)}")
        cases = [index[case_id] for case_id in ids]
        if not all(case["question_targets"] for case in cases):
            raise CommandError("Todos los casos smoke requieren QuestionTarget.")
        run_dir, summary = run_v3_cases(cases, options["output_root"])
        self.stdout.write(self.style.SUCCESS(
            f"V3_SMOKE={summary['records_written']}/3 RUN={run_dir}"))
