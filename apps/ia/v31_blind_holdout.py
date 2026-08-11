import copy
import re

from .v3_development import v3_development_cases


def _state():
    return {"service":None,"service_date":None,"load":None,"staff":{"required":None},
            "additional_services":{"packing":None,"packing_required":None,
                "disassembly_required":None,"assembly_required":None},
            "locations":{"origin":{"district":None,"floor":None,"elevator":None,
                "truck_access":None,"carry_distance_m":None,"access_observation":None},
                "destination":{"district":None,"floor":None,"elevator":None,
                "truck_access":None,"carry_distance_m":None,"access_observation":None}}}


def _case(index,message,expected,*,question="",targets=(),ambiguities=(),
          correction=False,human_review=False,state=None):
    return {"id":f"h31_{index:03d}","source":"synthetic_blind",
        "message":message,"expected":expected,"forbidden":{},
        "expected_ambiguities":list(ambiguities),"expected_correction":correction,
        "human_review":human_review,"state":copy.deepcopy(state or _state()),
        "last_bot_question":question,
        "question_targets":[{"field":field,"ref":ref,"operation":"set"}
                            for field,ref in targets],
        "recent_turns":([{"role":"assistant","content":question}] if question else [])}


def v31_blind_holdout_cases():
    cases=[]; add=lambda *args,**kwargs: cases.append(_case(len(cases)+1,*args,**kwargs))
    direct=[
        ("Necesito mudar mi depa; van sofá, mesa y ocho cajas",{"service":"mudanza","load":"sofá mesa ocho cajas"}),
        ("Es un traslado chico: una bici y tres paquetes",{"service":"traslado pequeno","load":"bici tres paquetes"}),
        ("Movemos la oficina con escritorios y archivadores",{"service":"oficina","load":"escritorios archivadores"}),
        ("Requiero transporte de mercadería: doce sacos de arroz",{"service":"carga","load":"doce sacos de arroz"}),
        ("Quiero llevar solo un ropero y una tele",{"service":"traslado pequeno","load":"ropero tele"}),
        ("Mudanza familiar con dos camas, refri y veinte cajas",{"service":"mudanza","load":"dos camas refri veinte cajas"}),
        ("Cambio de oficina, llevamos seis sillas y dos computadoras",{"service":"oficina","load":"seis sillas dos computadoras"}),
        ("Necesito carga para cuatro pallets de bebidas",{"service":"carga","load":"cuatro pallets bebidas"}),
        ("Solo traslado una lavadora y unas bolsas",{"service":"traslado pequeno","load":"lavadora bolsas"}),
        ("Me mudo con comedor, cómoda y cajas de ropa",{"service":"mudanza","load":"comedor cómoda cajas ropa"}),
    ]
    for message,expected in direct:add(message,expected)
    routes=[("Pueblo Libre","Barranco"),("Breña","San Miguel"),("Chorrillos","Lince"),
        ("Jesús María","Surquillo"),("San Luis","Magdalena"),("Rímac","San Borja"),
        ("La Victoria","Pueblo Libre"),("Barranco","Ate"),("Callao","Chorrillos"),
        ("Surquillo","La Molina")]
    for origin,destination in routes:
        add(f"Recojo en {origin} y entrega en {destination}",
            {"locations.origin.district":origin,"locations.destination.district":destination})
    access=[
        ("Origen quinto piso con ascensor; destino planta baja",5,True,0,None),
        ("Salimos de un segundo sin ascensor y llegamos a un sexto con ascensor",2,False,6,True),
        ("En origen piso 9 con elevador, en destino piso 3 sin elevador",9,True,3,False),
        ("Recojo en primer piso; entrega en octavo, ambos con ascensor",1,True,8,True),
        ("Origen planta baja y destino cuarto piso sin ascensor",0,None,4,False),
        ("Salida piso doce con ascensor, llegada piso siete con ascensor",12,True,7,True),
        ("En el primer lugar tercer piso sin ascensor; segundo lugar quinto con ascensor",3,False,5,True),
        ("Origen 10mo sin ascensor, destino 2do también sin ascensor",10,False,2,False),
        ("Se carga en piso seis con ascensor y se descarga en planta baja",6,True,0,None),
        ("Partimos del cuarto piso; al llegar es primer piso, ninguno tiene ascensor",4,False,1,False),
    ]
    for message,fo,eo,fd,ed in access:
        expected={"locations.origin.floor":fo,"locations.destination.floor":fd}
        if eo is not None:expected["locations.origin.elevator"]=eo
        if ed is not None:expected["locations.destination.elevator"]=ed
        add(message,expected)
    contextual_elevator=[("Sí, en ambos",True,"both"),("nop, en ninguno",False,"both"),
        ("en el primero sí",True,"origin"),("en el segundo no",False,"destination"),
        ("origen sí; destino no",None,"split"),("solo el de llegada tiene",None,"destination_true"),
        ("solo salida no tiene",None,"origin_false"),("sí tienen los dos",True,"both"),
        ("ninguno, toca escalera",False,"both"),("en uno hay, no recuerdo cuál",None,"ambiguous")]
    for message,value,kind in contextual_elevator:
        expected={};ambiguities=()
        if kind=="both":expected={"locations.origin.elevator":value,"locations.destination.elevator":value}
        elif kind=="origin":expected={"locations.origin.elevator":value}
        elif kind=="destination":expected={"locations.destination.elevator":value}
        elif kind=="split":expected={"locations.origin.elevator":True,"locations.destination.elevator":False}
        elif kind=="destination_true":expected={"locations.destination.elevator":True}
        elif kind=="origin_false":expected={"locations.origin.elevator":False}
        else:ambiguities=("elevator",)
        add(message,expected,question="¿Hay ascensor en ambos lugares?",
            targets=(("elevator","both"),),ambiguities=ambiguities,
            human_review=bool(ambiguities))
    contextual_truck=[
        ("sí, en los dos",{"locations.origin.truck_access":True,"locations.destination.truck_access":True},()),
        ("en salida entra, al llegar queda lejos",{"locations.origin.truck_access":True,"locations.destination.access_observation":"queda lejos"},()),
        ("solo entra en el segundo",{"locations.origin.truck_access":False,"locations.destination.truck_access":True},()),
        ("en ninguno entra",{"locations.origin.truck_access":False,"locations.destination.truck_access":False},()),
        ("origen normal, destino queda a media cuadra",{"locations.origin.truck_access":True,"locations.destination.access_observation":"media cuadra"},()),
        ("allá sí puede entrar",{"locations.destination.truck_access":True},()),
        ("acá no entra ni de broma",{"locations.origin.truck_access":False},()),
        ("en uno se puede, no sé cuál",{},("truck_access",)),
        ("ambos quedan algo retirados",{"locations.origin.access_observation":"retirados","locations.destination.access_observation":"retirados"},()),
        ("primero a 70 metros; segundo entra a la puerta",{"locations.origin.carry_distance_m":70,"locations.destination.truck_access":True},()),
    ]
    for message,expected,ambiguities in contextual_truck:
        add(message,expected,question="¿El camión puede entrar en origen y destino?",
            targets=(("truck_access","both"),),ambiguities=ambiguities,
            human_review=bool(ambiguities))
    packing_staff=[
        ("sí, embalaje básico",{"packing.required":True,"packing.mode":"embalaje basico"},"packing_mode"),
        ("sin embalaje porfa",{"packing.required":False},"packing_required"),
        ("quiero embalaje full",{"packing.required":True,"packing.mode":"embalaje full"},"packing_mode"),
        ("solo embalen muebles y artefactos",{"packing.required":True,"packing.mode":"embalaje de muebles y artefactos"},"packing_mode"),
        ("sí quiero que embalen, aún no sé cómo",{"packing.required":True},"packing_required"),
        ("necesito dos operarios de ustedes",{"staff.required":True},"staff_required"),
        ("yo llevo gente para cargar",{"staff.required":False},"staff_required"),
        ("sin personal, nosotros cargamos",{"staff.required":False},"staff_required"),
        ("sí, manden personal para carga",{"staff.required":True},"staff_required"),
        ("tal vez necesite ayudantes, confirmo luego",{},"staff_required"),
    ]
    for message,expected,target in packing_staff:
        add(message,expected,question="Confirma embalaje o personal requerido",
            targets=((target,None),))
    corrections=[
        ("Corrijo: origen es Comas, no Independencia",{"locations.origin.district":"Comas"}),
        ("Me confundí, destino es San Isidro",{"locations.destination.district":"San Isidro"}),
        ("Cambio: en origen sí hay ascensor",{"locations.origin.elevator":True}),
        ("No era quinto, es séptimo piso al llegar",{"locations.destination.floor":7}),
        ("Finalmente no quiero embalaje",{"packing.required":False}),
        ("Rectifico, sí necesito personal",{"staff.required":True}),
        ("La fecha cambia al martes",{"service_date":"relative:tuesday"}),
        ("No son cajas: llevo tres maletas",{"load":"tres maletas"}),
        ("Corrección, el camión sí entra en destino",{"locations.destination.truck_access":True}),
        ("Era mudanza, no traslado pequeño",{"service":"mudanza"}),
    ]
    for message,expected in corrections:
        add(message,expected,question="Confirma el dato anterior",
            targets=((next(iter(expected)).split(".")[-1],None),),correction=True)
    dates=[("el 3 de octubre de 2026","2026-10-03"),("para este miércoles","relative:wednesday"),
        ("el próximo sábado","relative:saturday"),("para mañana","relative:tomorrow"),
        ("el 21 de noviembre de 2026","2026-11-21"),("el lunes que viene","relative:monday"),
        ("para el 9 de diciembre de 2026","2026-12-09"),("este jueves","relative:thursday"),
        ("el próximo viernes","relative:friday"),("el 14 de enero de 2027","2027-01-14")]
    for message,value in dates:
        add(message,{"service_date":value},question="¿Para qué fecha sería?",
            targets=(("service_date",None),))
    ambiguities=["queda lejitos","el camión para media cuadra antes","ahí no entra",
        "es un tercer piso","sí tiene ascensor","queda a unos 40 metros","no hay elevador",
        "se estaciona pasando la esquina","entra sin problema","es planta baja"]
    fields=["access_observation","access_observation","truck_access","floor","elevator",
            "carry_distance_m","elevator","access_observation","truck_access","floor"]
    for message,field in zip(ambiguities,fields):
        add(message,{},ambiguities=(field,),human_review=True)
    multi=[
        ("Mudanza de Lince a Breña: cama, refri y diez cajas",{"service":"mudanza","locations.origin.district":"Lince","locations.destination.district":"Breña","load":"cama refri diez cajas"}),
        ("Es carga de cinco sacos; recojo Callao, entrega Rímac",{"service":"carga","load":"cinco sacos","locations.origin.district":"Callao","locations.destination.district":"Rímac"}),
        ("Origen piso 3 con ascensor; destino piso 6 sin ascensor; llevo un sofá",{"locations.origin.floor":3,"locations.origin.elevator":True,"locations.destination.floor":6,"locations.destination.elevator":False,"load":"sofá"}),
        ("Nosotros cargamos y queremos embalaje full para una vitrina",{"staff.required":False,"packing.required":True,"packing.mode":"embalaje full","load":"vitrina"}),
        ("En salida entra camión; llegada queda a 55 metros",{"locations.origin.truck_access":True,"locations.destination.carry_distance_m":55}),
        ("Traslado pequeño de Surco a San Luis, una bici, para el jueves",{"service":"traslado pequeno","locations.origin.district":"Surco","locations.destination.district":"San Luis","load":"bici","service_date":"relative:thursday"}),
        ("Oficina: Barranco a Miraflores, cuatro escritorios, sin embalaje",{"service":"oficina","locations.origin.district":"Barranco","locations.destination.district":"Miraflores","load":"cuatro escritorios","packing.required":False}),
        ("Mudanza, yo pongo cargadores; dos camas y una mesa",{"service":"mudanza","staff.required":False,"load":"dos camas una mesa"}),
        ("Destino segundo piso con ascensor y el camión estaciona a 30 metros",{"locations.destination.floor":2,"locations.destination.elevator":True,"locations.destination.carry_distance_m":30}),
        ("Recojo en Ate planta baja; entrega en La Molina cuarto sin ascensor",{"locations.origin.district":"Ate","locations.origin.floor":0,"locations.destination.district":"La Molina","locations.destination.floor":4,"locations.destination.elevator":False}),
    ]
    for message,expected in multi:add(message,expected)
    _validate_frozen_holdout(cases)
    return cases


def _validate_frozen_holdout(cases):
    assert len(cases)==100
    messages=[case["message"].strip().casefold() for case in cases]
    assert len(messages)==len(set(messages))
    assert sum(bool(case["question_targets"]) for case in cases)>=50
    development={case["message"].strip().casefold() for case in v3_development_cases()}
    assert not development.intersection(messages)
    pii=re.compile(r"@|https?://|(?:\+?51)?9\d{8}|\b\d{8}\b")
    assert not any(pii.search(case["message"]) for case in cases)
