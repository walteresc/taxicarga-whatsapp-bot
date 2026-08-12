import copy
import hashlib
import json
import re

from .v31_blind_holdout_round5 import v31_blind_holdout_round5_cases
from .v3_development import v3_development_cases


_MESSAGES = """
Necesito hacer una mudanza
Es un traslado chico
Quiero trasladar una oficina
Necesito mover carga
Lo mío sería mudanza
Solo es un traslado pequeño
Es para una oficina
El servicio es carga
Sí, queda como mudanza
Confirmado, traslado pequeño
Voy a llevar dos mesas de noche
También va una congeladora
Tengo 17 cajas
Hay un piano parado
Son 3 escritorios
Llevo cocina y balón sin gas
Además van cuatro maletas
Es un sillón seccional
Tengo seis bultos cerrados
También una mesa con vidrio
Lo necesito para el 6 de febrero de 2027
Sería este martes
Puede ser el domingo que viene
Lo quiero para mañana
Agéndalo para el 22 de marzo de 2027
Sale de un piso once
Llega a planta baja
En la salida sí hay ascensor
En la llegada no hay ascensor
Recojo en Huaycán
Entrego en Pachacámac
En destino sí ingresa el camión
En origen el camión no puede entrar
En la llegada son 45 metros de acarreo
Desde la salida hay 80 metros
En origen queda a media cuadra
Al llegar estaciona después de la esquina
Partimos desde Ancón
Terminamos en Santa Rosa
El destino es tercer piso
Sí, correcto
No, correcto
Claro
Para nada
Sí en ambos
Ninguno cuenta con ascensor
Únicamente el origen sí
En el destino no
Los dos tienen ascensor
Hay en uno, pero no sé en cuál
Sí puede ingresar
No puede ingresar
En los dos puede entrar
No entra en ninguno
Entra solamente por origen
En destino está bien retirado
Allá sí puede ingresar
Acá no puede pasar
En uno sí entra, no recuerdo cuál
El segundo queda a 60 metros
Sí, necesito apoyo de ustedes
No, la carga la hago yo
Envíenme operarios
Los cargadores los ponemos nosotros
Quiero personal de TaxiCarga
No necesito ayudantes
Por favor manden dos operarios
Mi familia hará la carga
Sí voy a requerir ayuda
Quizá, aún no lo tengo claro
No quiero embalaje
Sí necesito que embalen
Quiero embalaje básico
Prefiero embalaje completo
Empaquen muebles y electrodomésticos
No empaquen nada
Sí deseo embalaje, falta elegir modalidad
El básico está bien
Deseo la opción completa
Todavía estoy indeciso
Me corrijo: el origen es Carabayllo
Rectifico, la llegada es Chaclacayo
Cambio el dato: origen sí tiene ascensor
En realidad era noveno piso en destino
Finalmente voy a necesitar embalaje
Mejor no manden personal
Cambien la fecha al siguiente lunes
El sofá ya no va; ahora llevo una banca
Corrijo: el camión no entra por el origen
No corresponde a carga sino a mudanza
Está algo retirado
Es el quinto piso
Sí cuenta con ascensor
El camión no logra entrar
La distancia es 35 metros
Ahí está un poco lejos
Queda en planta baja
No cuenta con ascensor
Puede estacionar cerquita
Sí logra ingresar
""".strip().splitlines()


def v31_blind_holdout_round7_cases():
    cases=copy.deepcopy(v31_blind_holdout_round5_cases())
    assert len(_MESSAGES)==len(cases)==100
    for index,(case,message) in enumerate(zip(cases,_MESSAGES),1):
        case["id"]=f"h37_{index:03d}"
        case["source"]="synthetic_blind_round7"
        case["message"]=message
    _validate(cases)
    return cases


def dataset_hash(cases=None):
    payload=json.dumps(cases or v31_blind_holdout_round7_cases(),ensure_ascii=False,
                       sort_keys=True,separators=(",",":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate(cases):
    assert len(cases)==100
    assert sum(bool(case["question_targets"]) for case in cases)==50
    messages={case["message"].strip().casefold() for case in cases}
    assert len(messages)==100
    prior={case["message"].strip().casefold()
           for case in v31_blind_holdout_round5_cases()}
    development={case["message"].strip().casefold()
                 for case in v3_development_cases()}
    assert not messages.intersection(prior|development)
    pii=re.compile(r"@|https?://|(?:\+?51)?9\d{8}|\b\d{8}\b")
    assert not any(pii.search(case["message"]) for case in cases)
