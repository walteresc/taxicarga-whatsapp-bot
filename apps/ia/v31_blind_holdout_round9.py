import copy
import hashlib
import json
import re

from .v31_blind_holdout_round8 import v31_blind_holdout_round8_cases
from .v31_blind_holdout_round7 import v31_blind_holdout_round7_cases
from .v31_blind_holdout_round6 import v31_blind_holdout_round6_cases
from .v31_blind_holdout_round5 import v31_blind_holdout_round5_cases
from .v31_blind_holdout_round4 import v31_blind_holdout_round4_cases
from .v31_blind_holdout_round3 import v31_blind_holdout_round3_cases
from .v31_blind_holdout_round2 import v31_blind_holdout_round2_cases
from .v31_blind_holdout import v31_blind_holdout_cases
from .v3_development import v3_development_cases


_MESSAGES="""
El servicio que busco es una mudanza
Deseo cotizar un traslado pequeño
Vamos a cambiar de oficina
Es un trabajo de carga
Confirmo que se trata de mudanza
Mi pedido corresponde a traslado pequeño
Necesitamos mover la oficina
Clasifícalo como carga
Sí, el tipo correcto es mudanza
Queda definido como traslado pequeño
Transporto dos veladores
Hay una congeladora en la carga
La carga contiene diecisiete cajas
Debemos llevar un piano vertical
Van tres escritorios
Transportaré una cocina y un balón vacío
Se incluyen cuatro maletas
Moveremos un sofá seccional
Son seis paquetes cerrados
Incluye una mesa de vidrio
Quiero el servicio el 6 de febrero de 2027
La fecha sería este martes
Prefiero el próximo domingo
La fecha solicitada es mañana
Hagámoslo el 22 de marzo de 2027
En origen es piso once
El destino está en planta baja
Origen cuenta con ascensor
Destino no cuenta con ascensor
Salimos desde Huaycán
Llegamos a Pachacámac
En la llegada entra el camión
En la salida no entra el camión
El acarreo de destino es de 45 metros
El acarreo de origen es de 80 metros
El camión queda a media cuadra en origen
En la llegada queda pasando la esquina
El recojo es en Ancón
La descarga es en Santa Rosa
Llegamos a un tercer piso
Sí, así es
No, no hay
Sí, claro
No, de ninguna manera
Los dos sí tienen
Los dos están sin ascensor
Hay solamente en origen
No hay en la llegada
Sí hay ascensor en los dos
Uno de ellos tiene, no identifico cuál
Sí entra por la salida
No entra por la llegada
Puede entrar en ambos lugares
No puede entrar en ninguno
Por el origen sí; por el destino no
En la llegada estaciona lejos
En destino sí puede pasar
En origen no puede pasar
Puede pasar en uno, pero ignoro cuál
En el segundo punto hay 60 metros
Sí quiero que manden personal
No necesito personal, yo cargo
Necesito operarios para cargar
Mis cargadores se encargan
Requiero personal de TaxiCarga
Háganlo sin ayudantes
Manden dos operarios, por favor
Los míos hacen la carga
Necesito ayuda de carga
Quizá pida operarios, no está decidido
Lo quiero sin embalaje
Necesito servicio de embalaje
La modalidad será embalaje básico
La modalidad será embalaje full
Solicito embalaje de muebles y artefactos
Nada debe ser embalado
Sí al embalaje; la modalidad queda pendiente
Me sirve el embalaje básico
Contrato embalaje full
No he decidido si quiero embalaje
Corrección: salimos de Carabayllo
Me corrijo: el destino es Chaclacayo
Rectifico, en origen hay ascensor
El piso correcto del destino es nueve
Cambio mi respuesta: sí requiero embalaje
Rectifico, ya no necesito personal
Cambiemos el servicio al próximo lunes
Retiro el sofá de la lista y agrego una banca
Actualizo el acceso: el camión no entra en origen
Rectifico el servicio: es mudanza, no carga
Se encuentra lejos
Queda en el piso quinto
Ese sitio sí tiene ascensor
Por ahí no puede entrar el camión
Son 35 metros de recorrido
Queda retirado de la entrada
Se ubica en planta baja
Ahí no existe ascensor
Puede dejar el vehículo cerca
El camión sí entra
""".strip().splitlines()


def v31_blind_holdout_round9_cases():
    cases=copy.deepcopy(v31_blind_holdout_round8_cases())
    assert len(_MESSAGES)==len(cases)==100
    for index,(case,message) in enumerate(zip(cases,_MESSAGES),1):
        case["id"]=f"h39_{index:03d}"
        case["source"]="synthetic_blind_round9"
        case["message"]=message
    _validate(cases)
    return cases


def dataset_hash(cases=None):
    payload=json.dumps(cases or v31_blind_holdout_round9_cases(),ensure_ascii=False,
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
             v3_development_cases())
    prior={case["message"].strip().casefold() for source in sources for case in source}
    assert not messages & prior
    pii=re.compile(r"@|https?://|(?:\+?51)?9\d{8}|\b\d{8}\b")
    assert not any(pii.search(case["message"]) for case in cases)
