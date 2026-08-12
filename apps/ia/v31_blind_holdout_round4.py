import copy
import re

from .v31_blind_holdout import _state
from .v31_blind_holdout_round3 import v31_blind_holdout_round3_cases
from .v3_development import v3_development_cases


def _case(cases,message,expected,*,question="",target=None,ambiguity=None,
          correction=False,human=False):
    index=len(cases)+1
    cases.append({"id":f"h34_{index:03d}","source":"synthetic_blind_round4",
        "message":f"Cliente comenta: {message}","expected":expected,"forbidden":{},
        "expected_ambiguities":[ambiguity] if ambiguity else [],
        "expected_correction":correction,"human_review":human,
        "state":copy.deepcopy(_state()),"last_bot_question":question,
        "question_targets":[{"field":target[0],"ref":target[1],"operation":"set"}]
                           if target else [],
        "recent_turns":[{"role":"assistant","content":question}] if question else []})


def v31_blind_holdout_round4_cases():
    cases=[]
    services=[("Quiero hacer una mudanza de depa","mudanza"),
        ("Necesito trasladar una sola cómoda","traslado pequeno"),
        ("Es un servicio para mudar la oficina","oficina"),
        ("Busco transporte de carga comercial","carga"),
        ("Voy a mudarme este mes","mudanza"),("Solo traslado un colchón","traslado pequeno"),
        ("Movemos nuestra oficina pequeña","oficina"),("Tengo carga de mercadería","carga"),
        ("Es mudanza de vivienda","mudanza"),("Quiero mover un único ropero","traslado pequeno")]
    for msg,val in services:_case(cases,msg,{"service":val})
    loads=["dos veladores","una congeladora","diecisiete cajas","un piano vertical",
        "tres escritorios","una cocina y un balón vacío","cuatro maletas","un sofá seccional",
        "seis paquetes cerrados","una mesa de vidrio"]
    for value in loads:_case(cases,f"La carga es {value}",{"load":value})
    dates=[("Será el 6 de febrero de 2027","2027-02-06"),("Lo quiero este martes","relative:tuesday"),
        ("Agéndalo para el próximo domingo","relative:sunday"),("Sería mañana","relative:tomorrow"),
        ("La fecha es 22 de marzo de 2027","2027-03-22")]
    for msg,val in dates:_case(cases,msg,{"service_date":val})
    locations=[
        ("En origen es piso 11",{"locations.origin.floor":11}),
        ("El destino queda en planta baja",{"locations.destination.floor":0}),
        ("En salida sí hay ascensor",{"locations.origin.elevator":True}),
        ("En la llegada no existe elevador",{"locations.destination.elevator":False}),
        ("Origen: Huaycán",{"locations.origin.district":"Huaycán"}),
        ("Destino: Pachacámac",{"locations.destination.district":"Pachacámac"}),
        ("En destino el camión entra",{"locations.destination.truck_access":True}),
        ("En origen no puede entrar el camión",{"locations.origin.truck_access":False}),
        ("En la llegada se caminan 45 metros",{"locations.destination.carry_distance_m":45}),
        ("En la salida queda a 80 metros",{"locations.origin.carry_distance_m":80}),
        ("El origen queda media cuadra retirado",{"locations.origin.access_observation":"media cuadra"}),
        ("En destino se estaciona pasando la esquina",{"locations.destination.access_observation":"pasando la esquina"}),
        ("Recojo en Ancón",{"locations.origin.district":"Ancón"}),
        ("Entrego en Santa Rosa",{"locations.destination.district":"Santa Rosa"}),
        ("El punto de llegada es tercer piso",{"locations.destination.floor":3}),
    ]
    for msg,expected in locations:_case(cases,msg,expected)
    elevator=[("sí","origin",True),("no","origin",False),("claro que sí","destination",True),
        ("para nada","destination",False),("en los dos sí","both",True),
        ("ninguno tiene","both",False),("solo origen sí","origin",True),
        ("destino no","destination",False),("ambos con ascensor","both",True),
        ("en uno hay, no ubico cuál","both",None)]
    for msg,ref,val in elevator:
        expected={} if val is None else ({f"locations.{ref}.elevator":val} if ref!="both" else
            {"locations.origin.elevator":val,"locations.destination.elevator":val})
        _case(cases,msg,expected,question="¿Hay ascensor?",target=("elevator",ref),
              ambiguity="elevator" if val is None else None,human=val is None)
    truck=[("sí entra","origin",True),("no entra","destination",False),
        ("en ambos entra","both",True),("en ninguno puede entrar","both",False),
        ("solo en origen entra","origin",True),("en destino queda lejos","destination",None),
        ("allá sí entra","destination",True),("acá no entra","origin",False),
        ("en uno entra, no sé cuál","both","amb"),("segundo a 60 metros","destination",60)]
    for msg,ref,val in truck:
        ambiguity=None
        if val=="amb":expected={};ambiguity="truck_access"
        elif val is None:expected={f"locations.{ref}.access_observation":"lejos"}
        elif isinstance(val,int) and not isinstance(val,bool):expected={f"locations.{ref}.carry_distance_m":val}
        elif ref=="both":expected={"locations.origin.truck_access":val,"locations.destination.truck_access":val}
        else:expected={f"locations.{ref}.truck_access":val}
        _case(cases,msg,expected,question="¿Puede entrar el camión?",target=("truck_access",ref),
              ambiguity=ambiguity,human=bool(ambiguity))
    staff=[("sí, necesito gente",True),("no, yo cargo",False),("manden operarios",True),
        ("nosotros ponemos cargadores",False),("con personal de ustedes",True),
        ("sin ayudantes",False),("dos operarios por favor",True),("mi familia carga",False),
        ("sí requiero apoyo",True),("tal vez, todavía no sé",None)]
    for msg,val in staff:_case(cases,msg,{} if val is None else {"staff.required":val},
        question="¿Necesitas personal de carga?",target=("staff_required",None),human=val is None)
    packing=[("sin embalaje",{"packing.required":False},"packing_required"),
        ("sí quiero embalaje",{"packing.required":True},"packing_required"),
        ("embalaje básico",{"packing.required":True,"packing.mode":"embalaje basico"},"packing_mode"),
        ("embalaje full",{"packing.required":True,"packing.mode":"embalaje full"},"packing_mode"),
        ("embalen muebles y artefactos",{"packing.required":True,"packing.mode":"embalaje de muebles y artefactos"},"packing_mode"),
        ("no embalen nada",{"packing.required":False},"packing_required"),
        ("sí, pero modalidad pendiente",{"packing.required":True},"packing_required"),
        ("básico nomás",{"packing.required":True,"packing.mode":"embalaje basico"},"packing_mode"),
        ("quiero el completo",{"packing.required":True,"packing.mode":"embalaje full"},"packing_mode"),
        ("aún no decido",{},"packing_required")]
    for msg,expected,field in packing:_case(cases,msg,expected,
        question="¿Qué embalaje requieres?",target=(field,None),human=not expected)
    corrections=[
        ("Corrijo, origen es Carabayllo",{"locations.origin.district":"Carabayllo"}),
        ("Rectifico: destino es Chaclacayo",{"locations.destination.district":"Chaclacayo"}),
        ("Cambio, origen sí tiene ascensor",{"locations.origin.elevator":True}),
        ("Era piso nueve en destino",{"locations.destination.floor":9}),
        ("Finalmente sí quiero embalaje",{"packing.required":True}),
        ("Mejor sin personal",{"staff.required":False}),
        ("Cambiemos al próximo lunes",{"service_date":"relative:monday"}),
        ("No llevo sofá, llevo una banca",{"load":"una banca"}),
        ("Corrección: en origen no entra el camión",{"locations.origin.truck_access":False}),
        ("No es carga, es mudanza",{"service":"mudanza"}),
    ]
    for msg,expected in corrections:_case(cases,msg,expected,question="¿Confirmas el cambio?",
        target=(next(iter(expected)).split(".")[-1],None),correction=True)
    ambiguities=[("Queda algo lejos","access_observation"),("Es quinto piso","floor"),
        ("Sí tiene ascensor","elevator"),("El camión no entra","truck_access"),
        ("Son 35 metros","carry_distance_m"),("Ahí queda retirado","access_observation"),
        ("Es planta baja","floor"),("No hay ascensor","elevator"),
        ("Se estaciona cerca","access_observation"),("Sí puede entrar","truck_access")]
    for msg,field in ambiguities:_case(cases,msg,{},ambiguity=field,human=True)
    _validate(cases)
    return cases


def _validate(cases):
    assert len(cases)==100 and sum(bool(c["question_targets"]) for c in cases)==50
    messages={c["message"].strip().casefold() for c in cases};assert len(messages)==100
    prior={c["message"].strip().casefold() for c in v31_blind_holdout_round3_cases()}
    prior|={c["message"].strip().casefold() for c in v3_development_cases()}
    assert not messages.intersection(prior)
    pii=re.compile(r"@|https?://|(?:\+?51)?9\d{8}|\b\d{8}\b")
    assert not any(pii.search(c["message"]) for c in cases)
