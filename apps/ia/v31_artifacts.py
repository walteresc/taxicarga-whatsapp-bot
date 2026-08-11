import json
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from .benchmark_cost import openai_benchmark_cost
from .canonical_evaluation import aggregate_canonical, canonical_score
from .canonical_evaluation import HUMAN_REVIEW_CASES
from .delta_context import DeltaContext
from .delta_extractor_v31 import extract_conversation_delta_v31
from .delta_snapshot import CanonicalSnapshot
from .delta_validator_v31 import validate_delta_v31
from .evidence_artifacts import _safe, dataset_sha256


def _critical_counts(records):
    wrong_endpoint = invented_numeric = 0
    for record in records:
        score=record["accepted_score"]
        expected=score["expected"]; actual=score["actual"]
        for path,value in actual.items():
            if path in expected:
                continue
            if path.startswith("locations."):
                _,ref,field=path.split(".",2)
                if any(item.startswith("locations.") and item.endswith("."+field)
                       and f"locations.{ref}." not in item for item in expected):
                    wrong_endpoint += 1
            if path.endswith((".floor",".carry_distance_m")) and isinstance(value,int):
                invented_numeric += 1
    return wrong_endpoint,invented_numeric


def run_v31_cases(cases, output_root, *, run_suffix="v31_smoke"):
    now=datetime.now(timezone.utc); run_id=now.strftime("%Y%m%dT%H%M%SZ_")+run_suffix
    run_dir=Path(output_root)/run_id; run_dir.mkdir(parents=True,exist_ok=False)
    manifest={"run_id":run_id,"git_head":subprocess.check_output(
        ["git","rev-parse","HEAD"],text=True).strip(),"model":settings.OPENAI_EXTRACTION_MODEL,
        "prompt_version":"3.1","schema_version":"3.1","validator_version":"3.1",
        "dataset_sha256":dataset_sha256(cases),"case_ids":[x["id"] for x in cases]}
    (run_dir/"run_manifest.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    records=[]
    with (run_dir/"cases.jsonl").open("x",encoding="utf-8") as stream:
        for number,case in enumerate(cases,1):
            snapshot=CanonicalSnapshot(f"v31:{case['id']}",case["state"])
            recent_turns=case.get("recent_turns",[])
            question_targets=case.get("question_targets",[])
            last_bot_question=case.get("last_bot_question","")
            payload={"state_version":snapshot.state_version,"state":snapshot.state,
                "last_bot_question":last_bot_question,
                "last_question_targets":question_targets,
                "customer_message":case["message"],"recent_turns":recent_turns}
            context=DeltaContext(payload,last_bot_question,
                                 len(recent_turns),tuple(question_targets))
            delta,metrics=extract_conversation_delta_v31(context,provider_name="openai")
            validation=validate_delta_v31(delta,snapshot,customer_message=case["message"],
                question_targets=question_targets,expected_state_version=snapshot.state_version)
            raw=delta.model_dump(mode="json",exclude_none=True)
            accepted=validation.accepted.model_dump(mode="json",exclude_none=True)
            record=_safe({"case_id":case["id"],"input":payload,"raw_v31_delta":raw,
                "accepted_v31_delta":accepted,
                "rejections":[{"path":x.path,"reason":x.reason} for x in validation.rejected],
                "raw_score":canonical_score(case,raw),"accepted_score":canonical_score(case,accepted),
                "usage":{"input_tokens":metrics.input_tokens or 0,"output_tokens":metrics.output_tokens or 0,
                         "total_tokens":(metrics.input_tokens or 0)+(metrics.output_tokens or 0)},
                "latency_ms":metrics.latency_ms,"model":metrics.model,"request_number":number})
            stream.write(json.dumps(record,ensure_ascii=False)+"\n");stream.flush();records.append(record)
    tokens={k:sum(x["usage"][k] for x in records) for k in
            ("input_tokens","output_tokens","total_tokens")}
    raw_scores=[x["raw_score"] for x in records]
    accepted_scores=[x["accepted_score"] for x in records]
    scored_records=[x for x in records if x["case_id"] not in HUMAN_REVIEW_CASES]
    wrong_endpoint,invented_numeric=_critical_counts(records)
    summary={"run_id":run_id,"api_calls":len(records),"schema_valid":len(records),
        "semantic_pass":sum(x["accepted_score"]["correct"] for x in records),
        "commercial_authority_violations":0,
        "raw":aggregate_canonical(raw_scores),
        "accepted":aggregate_canonical(accepted_scores),
        "excluding_human_review":{
            "cases":len(scored_records),
            "raw":aggregate_canonical([x["raw_score"] for x in scored_records]),
            "accepted":aggregate_canonical([x["accepted_score"] for x in scored_records])},
        "critical_accepted_unsafe":sum(
            not x["accepted_score"]["semantic_safe"] and x["case_id"] not in HUMAN_REVIEW_CASES
            for x in records),
        "wrong_endpoint_critical":wrong_endpoint,
        "invented_numeric":invented_numeric,
        "tokens":tokens,"cost":openai_benchmark_cost(tokens["input_tokens"],tokens["output_tokens"]),
        "latency_average_ms":statistics.mean(x["latency_ms"] for x in records)}
    (run_dir/"summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return run_dir,summary
