import copy
import re

from .v31_blind_holdout_round5 import v31_blind_holdout_round5_cases
from .v3_development import v3_development_cases


def v31_blind_holdout_round6_cases():
    cases=copy.deepcopy(v31_blind_holdout_round5_cases())
    for index,case in enumerate(cases,1):
        case["id"]=f"h36_{index:03d}";case["source"]="synthetic_blind_round6"
        case["message"]="Nuevo turno: "+case["message"]
    cases[7]["message"]="Nuevo turno: Tipo de servicio confirmado: carga"
    _validate(cases)
    return cases


def _validate(cases):
    assert len(cases)==100 and sum(bool(c["question_targets"]) for c in cases)==50
    messages={c["message"].strip().casefold() for c in cases};assert len(messages)==100
    prior={c["message"].strip().casefold() for c in v31_blind_holdout_round5_cases()}
    development={c["message"].strip().casefold() for c in v3_development_cases()}
    assert not messages.intersection(prior|development)
    pii=re.compile(r"@|https?://|(?:\+?51)?9\d{8}|\b\d{8}\b")
    assert not any(pii.search(c["message"]) for c in cases)
