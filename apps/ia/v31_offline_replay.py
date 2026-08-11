import copy

from .delta_contract_v31 import ConversationDeltaV31


def adapt_v3_delta_to_v31(data):
    source = copy.deepcopy(data)
    output = {"schema_version":"3.1", "intent":source["intent"],
              "changes":{"lead":{},"locations":[]},
              "corrections":[],"ambiguities":[
                  {**{key:value for key,value in item.items() if key != "evidence"},
                   "evidence_quote":item.get("evidence", "")}
                  for item in source.get("ambiguities",[])]}
    for field, proposal in source.get("changes",{}).get("lead",{}).items():
        output["changes"]["lead"][field] = _proposal(proposal, numeric=False)
    for location in source.get("changes",{}).get("locations",[]):
        ref_type=location.get("ref_evidence_type","explicit")
        converted={"ref":location["ref"],
                   "ref_evidence_quote":location["ref_evidence"],
                   "ref_source":"explicit_message" if ref_type=="explicit"
                                else "question_target", "set":{}}
        for field, proposal in location.get("set",{}).items():
            converted["set"][field]=_proposal(
                proposal, numeric=field in {"floor","carry_distance_m"})
        output["changes"]["locations"].append(converted)
    for correction in source.get("corrections",[]):
        item={key:value for key,value in correction.items()
              if key not in {"evidence","evidence_type","context_dependency"}}
        item["evidence_quote"]=correction.get("evidence", "")
        item.update(_metadata(correction))
        output["corrections"].append(item)
    return ConversationDeltaV31.model_validate(output)


def _metadata(proposal):
    old=proposal.get("evidence_type","explicit")
    return {"evidence_type":"inferred" if old=="inferred" else "explicit",
            "context_dependency":"question_target" if old=="explicit_contextual"
                                 else "none"}


def _proposal(proposal, *, numeric):
    result={key:value for key,value in proposal.items()
            if key not in {"evidence","evidence_type","context_dependency"}}
    result["evidence_quote"]=proposal.get("evidence", "")
    result.update(_metadata(proposal))
    if numeric:
        result["value_origin"]="derived" if proposal.get("evidence_type")=="inferred" else "direct"
    return result
