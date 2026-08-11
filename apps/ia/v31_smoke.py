import copy


def _state():
    return {"service":None,"service_date":None,"load":None,"staff":{"required":None},
            "additional_services":{"packing":None,"packing_required":None,
                                   "disassembly_required":None,"assembly_required":None},
            "locations":{"origin":{"district":"Surco","floor":None,"elevator":None,
                                    "truck_access":None,"carry_distance_m":None,
                                    "access_observation":None},
                         "destination":{"district":"Miraflores","floor":None,"elevator":None,
                                         "truck_access":None,"carry_distance_m":None,
                                         "access_observation":None}}}


def _case(case_id,message,expected,targets=(),ambiguities=()):
    return {"id":case_id,"message":message,"expected":expected,"forbidden":{},
            "expected_ambiguities":list(ambiguities),"expected_correction":False,
            "state":copy.deepcopy(_state()),"last_bot_question":"logical target metadata",
            "question_targets":[{"field":f,"ref":r,"operation":"set"} for f,r in targets],
            "recent_turns":[]}


def v31_smoke_cases():
    return [
        _case("v31_context_extra","Sí, y además son 20 cajas",
              {"locations.origin.elevator":True,"load":"20 cajas"},
              (("elevator","origin"),)),
        _case("v31_staff_service_boundary","Necesito personal para cargar",
              {"staff.required":True},(("staff_required",None),)),
        _case("v31_load_staff_boundary",
              "Nosotros nos encargamos de cargar; llevo una refrigeradora",
              {"staff.required":False,"load":"refrigeradora"}),
        _case("v31_direct_distance","En destino son 65 metros desde donde estaciona",
              {"locations.destination.carry_distance_m":65}),
        _case("v31_endpoint_ambiguity","El camión queda lejos",{},
              ambiguities=("access_observation",)),
        _case("v31_explicit_truck_endpoint","En el origen el camión no entra",
              {"locations.origin.truck_access":False}),
        _case("v31_target_observation","Queda un poco lejos de la puerta",
              {"locations.destination.access_observation":"queda un poco lejos"},
              (("truck_access","destination"),)),
        _case("v31_packing_required_only","Sí quiero embalaje",
              {"packing.required":True},(("packing_required",None),)),
        _case("v31_service_date","Lo necesito para el 18 de septiembre de 2026",
              {"service_date":"2026-09-18"}),
        _case("v31_multi_field",
              "Es mudanza, llevo una cama y dos cajas; en destino es cuarto piso sin ascensor",
              {"service":"mudanza","load":"una cama y dos cajas",
               "locations.destination.floor":4,
               "locations.destination.elevator":False}),
    ]
