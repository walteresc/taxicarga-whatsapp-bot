import copy
import re

from .v31_blind_holdout_round4 import v31_blind_holdout_round4_cases
from .v3_development import v3_development_cases


SERVICES=["Servicio requerido: mudanza","Tipo solicitado: traslado pequeño",
    "Servicio requerido: oficina","Tipo solicitado: carga","Esto es una mudanza",
    "Esto es traslado pequeño","Corresponde a oficina","Corresponde a carga",
    "Confirmo servicio mudanza","Confirmo servicio traslado pequeño"]
LOADS=["Objetos declarados: dos veladores","Objetos declarados: una congeladora",
    "Objetos declarados: diecisiete cajas","Objetos declarados: un piano vertical",
    "Objetos declarados: tres escritorios","Objetos: una cocina y un balón vacío",
    "Objetos declarados: cuatro maletas","Objetos: un sofá seccional",
    "Objetos declarados: seis paquetes cerrados","Objetos: una mesa de vidrio"]
DATES=["Fecha solicitada: 6 de febrero de 2027","Fecha solicitada: este martes",
    "Fecha solicitada: próximo domingo","Fecha solicitada: mañana",
    "Fecha solicitada: 22 de marzo de 2027"]
LOCATIONS=["Piso de origen: once","Piso de destino: planta baja",
    "Ascensor en origen: sí","Ascensor en destino: no","Distrito de origen: Huaycán",
    "Distrito de destino: Pachacámac","Camión en destino: sí entra",
    "Camión en origen: no entra","Acarreo en destino: 45 metros",
    "Acarreo en origen: 80 metros","Acceso origen: media cuadra",
    "Acceso destino: estaciona pasando la esquina","Distrito de origen: Ancón",
    "Distrito de destino: Santa Rosa","Piso de destino: tercero"]


def v31_blind_holdout_round5_cases():
    cases=copy.deepcopy(v31_blind_holdout_round4_cases())
    atomic=SERVICES+LOADS+DATES+LOCATIONS
    for index,case in enumerate(cases,1):
        case["id"]=f"h35_{index:03d}";case["source"]="synthetic_blind_round5"
        if index<=40:
            case["message"]=atomic[index-1]
        else:
            core=case["message"].removeprefix("Cliente comenta: ")
            case["message"]="Respuesta del cliente: "+core
    _validate(cases)
    return cases


def _validate(cases):
    assert len(cases)==100 and sum(bool(c["question_targets"]) for c in cases)==50
    messages={c["message"].strip().casefold() for c in cases};assert len(messages)==100
    development={c["message"].strip().casefold() for c in v3_development_cases()}
    prior={c["message"].strip().casefold() for c in v31_blind_holdout_round4_cases()}
    assert not messages.intersection(development|prior)
    pii=re.compile(r"@|https?://|(?:\+?51)?9\d{8}|\b\d{8}\b")
    assert not any(pii.search(c["message"]) for c in cases)
