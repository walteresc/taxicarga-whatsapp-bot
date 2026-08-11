import copy
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.ia.blind_holdout import blind_holdout_cases
from apps.ia.delta_contract_v2 import ConversationDeltaV2
from apps.ia.delta_snapshot import CanonicalSnapshot
from apps.ia.delta_validator_v3 import validate_delta_v3
from apps.ia.evidence_artifacts import read_evidence_run
from apps.ia.management.commands.compare_delta_shadow import _apply_v2, aggregate, score


DEFAULT_RUN = Path("reports/ai_eval/20260811T192932Z_delta_v2_evidence")


def _aggregate_without(items, excluded):
    return aggregate([item for item in items if item["id"] != excluded])


class Command(BaseCommand):
    help = "Reproduce Validator V3 offline sobre raw del V2 evidence run."

    def add_arguments(self, parser):
        parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options):
        manifest, v2_summary, records = read_evidence_run(options["run"])
        cases = {case["id"]: case for case in blind_holdout_cases()}
        results = []
        unavailable = []
        contextual_unavailable = []
        for record in records:
            case = cases[record["case_id"]]
            targets = tuple(record["input_metadata"].get("question_targets") or ())
            if not targets:
                unavailable.append(case["id"])
                if case.get("last_bot_question"):
                    contextual_unavailable.append(case["id"])
            delta = ConversationDeltaV2.model_validate(record["raw_model_delta"])
            snapshot = CanonicalSnapshot(
                state_version=f"blind:{case['id']}", state=case["state"])
            validation = validate_delta_v3(
                delta, snapshot, customer_message=case["message"],
                question_targets=targets, expected_state_version=snapshot.state_version)
            state, changed = _apply_v2(copy.deepcopy(case["state"]), validation.accepted)
            evaluated = score(
                case, state, changed, [item.field for item in validation.accepted.ambiguities],
                validation.accepted.corrections)
            results.append({
                "id": case["id"], "score": evaluated,
                "accepted_delta": validation.accepted.model_dump(mode="json", exclude_none=True),
                "rejected": [{"path": item.path, "reason": item.reason}
                             for item in validation.rejected],
                "target_metadata_available": validation.target_metadata_available,
            })
        report = {
            "source_run": manifest["run_id"], "new_api_calls": 0,
            "target_metadata_available": len(records) - len(unavailable),
            "target_metadata_unavailable": unavailable,
            "contextual_cases_without_target_metadata": contextual_unavailable,
            "v2_accepted": v2_summary["accepted"],
            "v3_with_s02": aggregate(results),
            "v3_without_s02": _aggregate_without(results, "s02"),
            "results": results,
        }
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if options["output"]:
            options["output"].write_text(rendered + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Reporte V3: {options['output']}"))
        else:
            self.stdout.write(rendered)
