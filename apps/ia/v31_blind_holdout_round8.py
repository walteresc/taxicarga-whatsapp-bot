import copy
import hashlib
import json
import re

from .v31_blind_holdout import v31_blind_holdout_cases
from .v31_blind_holdout_round2 import v31_blind_holdout_round2_cases
from .v31_blind_holdout_round3 import v31_blind_holdout_round3_cases
from .v31_blind_holdout_round4 import v31_blind_holdout_round4_cases
from .v31_blind_holdout_round5 import v31_blind_holdout_round5_cases
from .v31_blind_holdout_round6 import v31_blind_holdout_round6_cases
from .v31_blind_holdout_round7 import v31_blind_holdout_round7_cases
from .v3_development import v3_development_cases


_MESSAGES = """
Hola, necesito el servicio de mudanza
Por favor cotízame un traslado pequeño
Se trata del traslado de una oficina
Necesito el servicio de carga
En resumen, esto es una mudanza
Lo requerido es un traslado pequeño
El trabajo corresponde a oficina
Confirma que el tipo es carga
De acuerdo, confirma mudanza
Entonces queda traslado pequeño
Para llevar son dos veladores
La carga incluye una congeladora
Voy a mover diecisiete cajas
También transporto un piano vertical
La lista tiene tres escritorios
Llevo una cocina y un balón vacío
En el camión van cuatro maletas
Hay que trasladar un sofá seccional
La carga son seis paquetes cerrados
Se transportará una mesa de vidrio
La fecha que necesito es 6 de febrero de 2027
Quisiera hacerlo este martes
Lo coordinamos para el próximo domingo
Necesito el traslado mañana
La fecha elegida es 22 de marzo de 2027
El recojo es en el piso once
La entrega queda en planta baja
Sí existe ascensor en el origen
En el destino no existe ascensor
El distrito de salida es Huaycán
El distrito de llegada es Pachacámac
El camión sí entra en destino
Por el origen no entra el camión
En destino hay 45 metros de acarreo
En origen el acarreo mide 80 metros
Desde el origen queda media cuadra
En destino estaciona pasando la esquina
La salida será desde Ancón
La entrega será en Santa Rosa
El lugar de destino está en el tercer piso
Sí, confirmado
No, confirmado
Claro que sí
No, para nada
En ambos sí hay
Ninguno de los dos tiene
Solo en el origen hay
En destino definitivamente no
Ambos cuentan con ascensor
Uno tiene, aunque no sé cuál
Sí, por origen entra
No, en destino no entra
En ambos extremos entra
En ninguno de los dos entra
Solamente entra en el origen
En el destino queda lejos
Allá sí entra el camión
Aquí no entra el camión
En uno puede entrar, no sé en cuál
En el segundo son exactamente 60 metros
Sí, necesito personal de apoyo
No, yo mismo hago la carga
Por favor envíen operarios
Nosotros aportamos los cargadores
Sí quiero personal de ustedes
Prefiero hacerlo sin ayudantes
Necesito dos operarios
La carga la hará mi familia
Sí requiero apoyo para cargar
Tal vez necesite gente, aún no sé
Definitivamente sin embalaje
Sí, requiero embalaje
Elijo embalaje básico
Elijo embalaje full
Necesito embalaje de muebles y artefactos
No quiero que embalen nada
Quiero embalaje, pero decidiré luego la modalidad
Para mí el embalaje básico
Me quedo con embalaje full
Todavía no decido sobre embalaje
Corrijo el dato: origen es Carabayllo
Rectificación: destino es Chaclacayo
Actualizo: en origen sí hay ascensor
Corrijo: destino está en el piso nueve
Finalmente confirmo que sí quiero embalaje
Cambio de idea: quiero el servicio sin personal
Corrijo la fecha al próximo lunes
Ya no llevo sofá; en su lugar va una banca
Rectifico: en origen no entra el camión
Corrección, no es carga sino mudanza
Queda bastante lejos
El inmueble está en quinto piso
Sí dispone de ascensor
No entra el camión
La distancia indicada es 35 metros
Ahí queda retirado
La ubicación es planta baja
Ese lugar no tiene ascensor
El vehículo estaciona cerca
Sí puede ingresar el camión
""".strip().splitlines()


def v31_blind_holdout_round8_cases():
    cases=copy.deepcopy(v31_blind_holdout_round5_cases())
    assert len(_MESSAGES)==len(cases)==100
    for index,(case,message) in enumerate(zip(cases,_MESSAGES),1):
        case["id"]=f"h38_{index:03d}"
        case["source"]="synthetic_blind_round8"
        case["message"]=message
    _validate(cases)
    return cases


def dataset_hash(cases=None):
    payload=json.dumps(cases or v31_blind_holdout_round8_cases(),ensure_ascii=False,
                       sort_keys=True,separators=(",",":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate(cases):
    assert len(cases)==100
    assert sum(bool(case["question_targets"]) for case in cases)==50
    assert sum(bool(case["human_review"]) for case in cases)==14
    messages={case["message"].strip().casefold() for case in cases}
    assert len(messages)==100
    prior_sets=(v31_blind_holdout_cases(),v31_blind_holdout_round2_cases(),
                v31_blind_holdout_round3_cases(),v31_blind_holdout_round4_cases(),
                v31_blind_holdout_round5_cases(),v31_blind_holdout_round6_cases(),
                v31_blind_holdout_round7_cases(),v3_development_cases())
    prior={case["message"].strip().casefold()
           for prior_cases in prior_sets for case in prior_cases}
    assert not messages.intersection(prior)
    pii=re.compile(r"@|https?://|(?:\+?51)?9\d{8}|\b\d{8}\b")
    assert not any(pii.search(case["message"]) for case in cases)
