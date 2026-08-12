import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.ia.blind_holdout import blind_holdout_cases
from apps.ia.canonical_evaluation import aggregate_canonical, canonical_score
from apps.ia.delta_snapshot import CanonicalSnapshot
from apps.ia.delta_contract_v31 import ConversationDeltaV31
from apps.ia.delta_validator_v31 import validate_delta_v31
from apps.ia.v31_offline_replay import adapt_v3_delta_to_v31
from apps.ia.v3_development import v3_development_cases
from apps.ia.v31_blind_holdout import v31_blind_holdout_cases
from apps.ia.v31_blind_holdout_round2 import v31_blind_holdout_round2_cases


class Command(BaseCommand):
    help="Replay offline de Validator V3.1 sobre raw V3 adaptado conservadoramente."

    def add_arguments(self,parser): parser.add_argument("run_dir",type=Path)

    def handle(self,*args,**options):
        run_dir=options["run_dir"]
        records=[json.loads(line) for line in
                 (run_dir/"cases.jsonl").read_text(encoding="utf-8").splitlines()]
        prefix=records[0]["case_id"].split("_",1)[0] if records else ""
        source_cases=(v31_blind_holdout_cases() if prefix == "h31" else
                      v31_blind_holdout_round2_cases() if prefix == "h32" else
                      v3_development_cases())
        cases={case["id"]:case for case in source_cases}
        rows=[]
        for record in records:
            case=cases[record["case_id"]]
            if "raw_v31_delta" in record:
                delta=ConversationDeltaV31.model_validate(record["raw_v31_delta"])
            else:
                delta=adapt_v3_delta_to_v31(record["raw_v3_delta"])
            result=validate_delta_v31(delta,CanonicalSnapshot(f"offline:{case['id']}",case["state"]),
                customer_message=case["message"],question_targets=case["question_targets"])
            dumped=result.accepted.model_dump(mode="json",exclude_none=True)
            rows.append({"case_id":case["id"],"score":canonical_score(case,dumped),
                         "rejections":[{"path":x.path,"reason":x.reason} for x in result.rejected]})
        scope=("validator-only; native V3.1 raw outputs"
               if records and "raw_v31_delta" in records[0]
               else "validator-only; old V3 metadata adapted")
        report={"source_run":run_dir.name,"scope":scope,
                "new_api_calls":0,"metrics":aggregate_canonical([x["score"] for x in rows]),
                "cases":rows}
        target=run_dir/"v31_validator_only_replay.json"
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"V31_VALIDATOR_REPLAY={target}"))
