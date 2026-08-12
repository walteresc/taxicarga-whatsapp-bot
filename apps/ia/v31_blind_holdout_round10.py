import copy
import hashlib
import json
import re

from .v31_blind_holdout import v31_blind_holdout_cases
from .v31_blind_holdout_round2 import v31_blind_holdout_round2_cases
from .v31_blind_holdout_round3 import v31_blind_holdout_round3_cases
from .v31_blind_holdout_round4 import v31_blind_holdout_round4_cases
from .v31_blind_holdout_round5 import v31_blind_holdout_round5_cases
from .v31_blind_holdout_round6 import v31_blind_holdout_round6_cases
from .v31_blind_holdout_round7 import v31_blind_holdout_round7_cases
from .v31_blind_holdout_round8 import v31_blind_holdout_round8_cases
from .v31_blind_holdout_round9 import v31_blind_holdout_round9_cases
from .v3_development import v3_development_cases


_LEAD_INS=("Para precisar: ","Te comento: ","Mi respuesta es: ",
           "Añado este dato: ","Dato actualizado: ")


def v31_blind_holdout_round10_cases():
    cases=copy.deepcopy(v31_blind_holdout_round8_cases())
    for index,case in enumerate(cases,1):
        case["id"]=f"h40_{index:03d}"
        case["source"]="synthetic_blind_round10"
        case["message"]=_LEAD_INS[(index-1)%len(_LEAD_INS)]+case["message"]
    _validate(cases)
    return cases


def dataset_hash(cases=None):
    payload=json.dumps(cases or v31_blind_holdout_round10_cases(),ensure_ascii=False,
                       sort_keys=True,separators=(",",":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _validate(cases):
    assert len(cases)==100
    assert sum(bool(case["question_targets"]) for case in cases)==50
    assert sum(bool(case["human_review"]) for case in cases)==14
    messages={case["message"].strip().casefold() for case in cases}
    assert len(messages)==100
    sources=(v31_blind_holdout_cases(),v31_blind_holdout_round2_cases(),
             v31_blind_holdout_round3_cases(),v31_blind_holdout_round4_cases(),
             v31_blind_holdout_round5_cases(),v31_blind_holdout_round6_cases(),
             v31_blind_holdout_round7_cases(),v31_blind_holdout_round8_cases(),
             v31_blind_holdout_round9_cases(),v3_development_cases())
    prior={case["message"].strip().casefold() for source in sources for case in source}
    assert not messages & prior
    pii=re.compile(r"@|https?://|(?:\+?51)?9\d{8}|\b\d{8}\b")
    assert not any(pii.search(case["message"]) for case in cases)
