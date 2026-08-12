import copy
import re

from .v31_blind_holdout import v31_blind_holdout_cases
from .v31_blind_holdout_round2 import v31_blind_holdout_round2_cases
from .v3_development import v3_development_cases


def v31_blind_holdout_round3_cases():
    starters=("Oe, ","Dato adicional: ","Para que apuntes: ","Te confirmo que ","En corto, ")
    endings=(".",", ya?",", eso es todo",", causa",", correcto")
    cases=[]
    for index,source in enumerate(v31_blind_holdout_cases(),1):
        case=copy.deepcopy(source)
        core=source["message"].strip().rstrip(".,")
        message=starters[(index*2)%5]+core[0].lower()+core[1:]+endings[(index*4)%5]
        if index%8==0:message=message.replace("para","pa")
        if index%9==0:message=message.replace("ascensor","ascensorcito")
        if index%13==0:message=message.replace("camión","camioncito")
        case.update(id=f"h33_{index:03d}",source="synthetic_blind_round3",message=message)
        if index==45:
            case["human_review"]=True
        cases.append(case)
    _validate(cases)
    return cases


def _validate(cases):
    assert len(cases)==100
    current={case["message"].strip().casefold() for case in cases}
    prior={case["message"].strip().casefold() for case in v31_blind_holdout_cases()}
    prior|={case["message"].strip().casefold() for case in v31_blind_holdout_round2_cases()}
    prior|={case["message"].strip().casefold() for case in v3_development_cases()}
    assert len(current)==100 and not current.intersection(prior)
    assert sum(bool(case["question_targets"]) for case in cases)>=50
    pii=re.compile(r"@|https?://|(?:\+?51)?9\d{8}|\b\d{8}\b")
    assert not any(pii.search(case["message"]) for case in cases)
