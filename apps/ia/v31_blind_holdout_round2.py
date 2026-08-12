import copy
import re

from .v31_blind_holdout import v31_blind_holdout_cases
from .v3_development import v3_development_cases


def _variant(message,index,contextual):
    prefixes=("Ya pe, ","Te cuento: ","Mira, ","Sería así: ","Confirmo: ")
    suffixes=(" nomás"," porfa",", eso sería",", gracias"," pues")
    value=prefixes[index%len(prefixes)]+message+suffixes[(index*3)%len(suffixes)]
    if index%6==0:value=value.replace("ascensor","asensor")
    if index%7==0:value=value.replace("camión","camion")
    if index%11==0:value=value.replace("destino","destno")
    if contextual and index%4==0:value="Sobre lo que preguntas, "+value.casefold()
    return value


def v31_blind_holdout_round2_cases():
    cases=[]
    for index,source in enumerate(v31_blind_holdout_cases(),1):
        case=copy.deepcopy(source)
        case["id"]=f"h32_{index:03d}"
        case["source"]="synthetic_blind_round2"
        case["message"]=_variant(source["message"],index,bool(source["question_targets"]))
        case["recent_turns"]=(
            [{"role":"assistant","content":source["last_bot_question"]}]
            if source["last_bot_question"] else [])
        cases.append(case)
    _validate(cases)
    return cases


def _validate(cases):
    assert len(cases)==100
    messages={case["message"].strip().casefold() for case in cases}
    assert len(messages)==100
    prior={case["message"].strip().casefold() for case in v31_blind_holdout_cases()}
    development={case["message"].strip().casefold() for case in v3_development_cases()}
    assert not messages.intersection(prior|development)
    assert sum(bool(case["question_targets"]) for case in cases)>=50
    pii=re.compile(r"@|https?://|(?:\+?51)?9\d{8}|\b\d{8}\b")
    assert not any(pii.search(case["message"]) for case in cases)
