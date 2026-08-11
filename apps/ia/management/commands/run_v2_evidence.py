from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ia.blind_holdout import blind_holdout_cases
from apps.ia.evidence_artifacts import dataset_sha256, run_evidence_cases


class Command(BaseCommand):
    help = "Persiste evidencia detallada e inmutable del holdout V2."

    def add_arguments(self, parser):
        parser.add_argument("--confirm-real-api", action="store_true")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--output-root", type=Path, default=Path("reports/ai_eval"))
        parser.add_argument("--hash-only", action="store_true")

    def handle(self, *args, **options):
        cases = blind_holdout_cases()
        if options["hash_only"]:
            self.stdout.write(dataset_sha256(cases))
            return
        if not options["confirm_real_api"]:
            raise CommandError("Use --confirm-real-api para autorizar OpenAI real.")
        limit = options.get("limit")
        if limit is not None and not 1 <= limit <= len(cases):
            raise CommandError("--limit debe estar entre 1 y 100.")
        selected = cases[:limit] if limit else cases
        suffix = "delta_v2_smoke" if limit else "delta_v2_evidence"
        run_dir, summary = run_evidence_cases(
            selected, options["output_root"], run_suffix=suffix)
        self.stdout.write(self.style.SUCCESS(
            f"RUN={summary['run_id']} PATH={run_dir} RECORDS={summary['records_written']} "
            f"HASH_MATCH={summary['dataset_hash_match']}"))
