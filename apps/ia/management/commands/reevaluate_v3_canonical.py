import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.ia.blind_holdout import blind_holdout_cases
from apps.ia.canonical_evaluation import (
    ACCEPTED_UNSAFE_ADJUDICATION, HUMAN_REVIEW_CASES, ORIGINAL_FN_CAUSES,
    PACKING_ADJUDICATION, REJECTION_AUDIT, aggregate_canonical, canonical_score,
)


class Command(BaseCommand):
    help = "Reevalúa artifacts V3 offline con representación semántica canónica."

    def add_arguments(self, parser):
        parser.add_argument("run_dir", type=Path)

    def handle(self, *args, **options):
        run_dir = options["run_dir"]
        cases = {case["id"]: case for case in blind_holdout_cases()}
        records = [json.loads(line) for line in
                   (run_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
        rows = []
        for record in records:
            case = cases[record["case_id"]]
            raw = canonical_score(case, record["raw_v3_delta"])
            accepted = canonical_score(case, record["accepted_v3_delta"])
            rows.append({"case_id": case["id"], "raw": raw, "accepted": accepted,
                         "human_review": HUMAN_REVIEW_CASES.get(case["id"])})
        non_human = [row for row in rows if not row["human_review"]]
        report = {
            "source_run": run_dir.name, "new_api_calls": 0,
            "raw": aggregate_canonical([row["raw"] for row in rows]),
            "accepted": aggregate_canonical([row["accepted"] for row in rows]),
            "excluding_human_review": {
                "raw": aggregate_canonical([row["raw"] for row in non_human]),
                "accepted": aggregate_canonical([row["accepted"] for row in non_human]),
            },
            "human_review": HUMAN_REVIEW_CASES, "cases": rows,
            "packing_adjudication": PACKING_ADJUDICATION,
            "accepted_unsafe_adjudication": ACCEPTED_UNSAFE_ADJUDICATION,
            "rejection_audit": REJECTION_AUDIT,
            "original_false_negative_causes": ORIGINAL_FN_CAUSES,
        }
        target = run_dir / "canonical_evaluation.json"
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"CANONICAL_EVALUATION={target}"))
