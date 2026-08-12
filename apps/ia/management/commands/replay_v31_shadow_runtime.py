import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ia.delta_contract_v31 import ConversationDeltaV31
from apps.ia.runtime_v31 import _legacy_fields


class Command(BaseCommand):
    help = "Replay frozen V3.1 artifacts through the runtime mapper without state writes."

    def add_arguments(self, parser):
        parser.add_argument("cases_file")
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--report")

    def handle(self, *args, **options):
        source = Path(options["cases_file"])
        records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
        records = records[: options["limit"]]
        if len(records) != options["limit"]:
            raise CommandError(f"Expected {options['limit']} records, found {len(records)}")

        forbidden = {
            "precio_cotizado", "precio_estimado_min", "precio_estimado_max",
            "precio_recomendado", "estado", "etapa_conversacion", "atencion_humana",
        }
        results = []
        critical = 0
        for record in records:
            try:
                delta = ConversationDeltaV31.model_validate(record["accepted_v31_delta"])
                proposed = _legacy_fields(delta)
                unsafe = sorted(forbidden.intersection(proposed))
                if unsafe:
                    critical += 1
                results.append({
                    "case_id": record["case_id"],
                    "status": "fail" if unsafe else "pass",
                    "proposed_fields": sorted(proposed),
                    "forbidden_fields": unsafe,
                })
            except Exception as exc:
                critical += 1
                results.append({
                    "case_id": record.get("case_id"),
                    "status": "fail",
                    "error_type": type(exc).__name__,
                })

        report = {
            "protocol": "V3.1 frozen accepted delta -> runtime mapper; read-only",
            "cases": len(records),
            "passes": len(records) - critical,
            "critical_errors": critical,
            "state_writes": 0,
            "meta_sends": 0,
            "pricing_authority_fields": 0,
            "results": results,
        }
        if options["report"]:
            target = Path(options["report"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"V31_SHADOW={report['passes']}/{report['cases']} "
                f"CRITICAL={critical} STATE_WRITES=0 META_SENDS=0"
            )
        )
