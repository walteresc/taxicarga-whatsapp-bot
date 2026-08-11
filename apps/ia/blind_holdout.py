import copy


def _state():
    return {
        "service": None,
        "service_date": None,
        "locations": {
            "origin": {"district": None, "floor": None, "elevator": None,
                       "truck_access": None, "carry_distance_m": None,
                       "access_observation": None},
            "destination": {"district": None, "floor": None, "elevator": None,
                            "truck_access": None, "carry_distance_m": None,
                            "access_observation": None},
        },
        "load": None,
        "staff": {"required": None},
        "additional_services": {"packing": None, "disassembly_required": None,
                                "packing_required": None,
                                "assembly_required": None},
    }


def _case(case_id, message, expected=None, *, question="", source="synthetic",
          forbidden=None, ambiguities=None, correction=False, state=None):
    return {
        "id": case_id, "message": message, "last_bot_question": question,
        "state": copy.deepcopy(state or _state()), "expected": expected or {},
        "forbidden": forbidden or {}, "expected_ambiguities": ambiguities or [],
        "expected_correction": correction, "source": source,
        "multiturn": bool(question),
    }


def blind_holdout_cases():
    real_specs = [
        ("r01", "Hola quiero cotizar", {}),
        ("r02", "Surco a La Molina", {"locations.origin.district": "Surco", "locations.destination.district": "La Molina"}),
        ("r03", "Un ropero, una cama y una lavadora", {"load": "ropero cama lavadora"}),
        ("r04", "del 3ro al 3ro", {"locations.origin.floor": 3, "locations.destination.floor": 3}, "¿De qué piso sale y a qué piso llega?"),
        ("r05", "ascensor", {"locations.origin.elevator": True}, "¿En el origen usan ascensor o escaleras?"),
        ("r06", "escaleras", {"locations.destination.elevator": False}, "¿En el destino usan ascensor o escaleras?"),
        ("r07", "si, con personal", {"staff.required": True}, "¿Solo transporte o también personal?"),
        ("r08", "con embalaje", {}, "¿Lo necesitas con embalaje o sin embalaje?"),
        ("r09", "solo lo mas fragil", {"additional_services.packing": "embalaje basico"}, "¿Qué tipo de embalaje necesitas?"),
        ("r10", "sin embalaje", {"additional_services.packing": "sin embalaje"}, "¿Qué tipo de embalaje necesitas?"),
        ("r11", "todo embalado", {"additional_services.packing": "embalaje full"}, "¿Qué tipo de embalaje necesitas?"),
        ("r12", "muebles y artefactos", {"additional_services.packing": "embalaje de muebles y artefactos"}, "¿Qué tipo de embalaje necesitas?"),
        ("r13", "Hola", {}),
        ("r14", "solo transporte", {"staff.required": False}, "¿Solo transporte o también personal?"),
        ("r15", "quiero cotizar un traslado", {"service": "traslado pequeno"}),
        ("r16", "no, sin embalaje", {"additional_services.packing": "sin embalaje"}, "¿Lo necesitas con embalaje?"),
        ("r17", "con personal", {"staff.required": True}, "¿Solo transporte o también personal?"),
        ("r18", "si, quiero", {}, "¿Quieres embalaje?"),
        ("r19", "quiero trasladar las cosas de un estudiante, una cama, un colchon, una tarima, cajas y otros muebles", {"service": "traslado pequeno", "load": "cama colchon tarima cajas muebles"}),
        ("r20", "de surco a la molina", {"locations.origin.district": "Surco", "locations.destination.district": "La Molina"}),
        ("r21", "del piso 10 al piso 9", {"locations.origin.floor": 10, "locations.destination.floor": 9}, "¿De qué piso sale y a cuál llega?"),
        ("r22", "ambos lugares son escaleras", {"locations.origin.elevator": False, "locations.destination.elevator": False}, "¿Usan ascensor o escaleras?"),
        ("r23", "sin embalaej", {"additional_services.packing": "sin embalaje"}, "¿Con embalaje o sin embalaje?"),
        ("r24", "no", {"additional_services.disassembly_required": False}, "¿Hay muebles que debamos desarmar?"),
        ("r25", "no se aun", {}, "¿Para qué fecha lo necesitas?"),
        ("r26", "es demasiado", {}), ("r27", "es mucho", {}),
        ("r28", "no gracias", {}), ("r29", "probando", {}),
        ("r30", "Surco a La Molina", {"locations.origin.district": "Surco", "locations.destination.district": "La Molina"}),
        ("r31", "del 3ro al 3ro", {"locations.origin.floor": 3, "locations.destination.floor": 3}, "¿Cuáles son ambos pisos?"),
        ("r32", "ascensor", {"locations.origin.elevator": True}, "¿Cómo bajamos la carga en origen?"),
        ("r33", "escaleras", {"locations.destination.elevator": False}, "¿Y en destino?"),
        ("r34", "si, con personal", {"staff.required": True}, "¿Necesitas operarios?"),
        ("r35", "solo lo mas fragil", {"additional_services.packing": "embalaje basico"}, "¿Qué embalaje prefieres?"),
        ("r36", "no", {"additional_services.assembly_required": False}, "¿Debemos volver a armar los muebles?"),
        ("r37", "una cama, un colchon y unas cajas", {"load": "cama colchon cajas"}),
        ("r38", "con personal", {"staff.required": True}, "¿Quién cargará?"),
        ("r39", "sin embalaje", {"additional_services.packing": "sin embalaje"}, "¿Requiere embalaje?"),
        ("r40", "escaleras en los dos", {"locations.origin.elevator": False, "locations.destination.elevator": False}, "¿Hay ascensor en ambos lugares?"),
    ]
    cases = []
    for spec in real_specs:
        case_id, message, expected, *question = spec
        cases.append(_case(case_id, message, expected, question=question[0] if question else "", source="historical_real_anonymized"))

    synthetic = [
        ("s01", "Necesito una mudanza de Pueblo Libre hacia Barranco", {"service":"mudanza","locations.origin.district":"Pueblo Libre","locations.destination.district":"Barranco"}),
        ("s02", "Es carga comercial, sale de Ate y va al Callao", {"service":"carga","locations.origin.district":"Ate","locations.destination.district":"Callao"}),
        ("s03", "Traslado de oficina desde San Borja hasta Lince", {"service":"oficina","locations.origin.district":"San Borja","locations.destination.district":"Lince"}),
        ("s04", "Solo moveré una cómoda y seis cajas", {"service":"traslado pequeno","load":"comoda seis cajas"}),
        ("s05", "Llevo una vitrina, dos mesas, ocho sillas y 24 cajas", {"load":"vitrina dos mesas ocho sillas 24 cajas"}),
        ("s06", "La máquina pesa 900 kg", {"load":"maquina 900 kg"}, "", {"locations.origin.floor":900,"locations.destination.floor":900}),
        ("s07", "Son como 20 cajas", {"load":"20 cajas"}, "", {"locations.origin.floor":20,"locations.destination.floor":20}),
        ("s08", "Sale del quinto y llega al primero", {"locations.origin.floor":5,"locations.destination.floor":1}, "¿Cuáles son los pisos?"),
        ("s09", "Origen piso doce, destino planta baja", {"locations.origin.floor":12,"locations.destination.floor":0}),
        ("s10", "En Magdalena es 4to con ascensor; en Jesús María 7mo sin ascensor", {"locations.origin.district":"Magdalena","locations.origin.floor":4,"locations.origin.elevator":True,"locations.destination.district":"Jesús María","locations.destination.floor":7,"locations.destination.elevator":False}),
        ("s11", "sí", {"locations.origin.elevator":True}, "¿El origen tiene ascensor?"),
        ("s12", "no", {"locations.destination.elevator":False}, "¿El destino tiene ascensor?"),
        ("s13", "ahí sí", {"locations.origin.truck_access":True}, "¿El camión puede entrar en origen?"),
        ("s14", "allá no", {"locations.destination.truck_access":False}, "¿El camión entra en destino?"),
        ("s15", "en los dos", {"locations.origin.elevator":True,"locations.destination.elevator":True}, "¿Hay ascensor en ambos?"),
        ("s16", "en el otro", {"locations.destination.elevator":True}, "¿En origen hay ascensor?"),
        ("s17", "creo que sí", {"locations.origin.elevator":True}, "¿Hay ascensor en origen?"),
        ("s18", "más o menos", {}, "¿El camión llega hasta la puerta?"),
        ("s19", "el camión queda lejos", {}, "", {}, ["access_observation"]),
        ("s20", "nosotros cargamos", {"staff.required":False}),
        ("s21", "en surco sí y allá no", {"locations.origin.elevator":True,"locations.destination.elevator":False}, "¿Hay ascensor en ambos?"),
        ("s22", "acá no, pero en el segundo sí", {"locations.origin.elevator":False,"locations.destination.elevator":True}, "¿Hay ascensor en origen y destino?"),
        ("s23", "el carro para a dos cuadras", {}, "", {"locations.origin.carry_distance_m":200,"locations.destination.carry_distance_m":200}, ["access_observation"]),
        ("s24", "en destino hay 65 metros desde donde estaciona", {"locations.destination.carry_distance_m":65}),
        ("s25", "puede estacionar pegado a la puerta en origen", {"locations.origin.truck_access":True}),
        ("s26", "en ambos queda un poco retirado", {"locations.origin.access_observation":"poco retirado","locations.destination.access_observation":"poco retirado"}),
        ("s27", "me equivoqué, no es Ate sino Santa Anita", {"locations.origin.district":"Santa Anita"}, "", {}, [], True),
        ("s28", "no era segundo, es sexto piso en destino", {"locations.destination.floor":6}, "", {}, [], True),
        ("s29", "corrijo: en origen no hay ascensor", {"locations.origin.elevator":False}, "", {}, [], True),
        ("s30", "al final sí requerimos embalaje completo", {"additional_services.packing":"embalaje full"}, "", {}, [], True),
        ("s31", "sin embalaje y sin desarmar nada", {"additional_services.packing":"sin embalaje","additional_services.disassembly_required":False}),
        ("s32", "hay que desarmar y luego armar el ropero", {"additional_services.disassembly_required":True,"additional_services.assembly_required":True}),
        ("s33", "desarmado sí, armado no", {"additional_services.disassembly_required":True,"additional_services.assembly_required":False}),
        ("s34", "quiero embalaje para muebles y artefactos", {"additional_services.packing":"embalaje de muebles y artefactos"}),
        ("s35", "yo pongo a las personas que cargan", {"staff.required":False}),
        ("s36", "manden operarios para cargar y descargar", {"staff.required":True}),
        ("s37", "quizá necesite gente, todavía no sé", {}),
        ("s38", "¿Cuánto cuesta el servicio?", {}),
        ("s39", "¿Trabajan los domingos?", {}),
        ("s40", "Antes de seguir, ¿emiten factura?", {}),
        ("s41", "lo necesito el 18 de septiembre", {"service_date":"2026-09-18"}),
        ("s42", "sería mañana por la tarde", {"service_date":"relative:tomorrow"}),
        ("s43", "todavía no tengo fecha", {}),
        ("s44", "cambiemos la fecha al viernes", {"service_date":"relative:friday"}, "", {}, [], True),
        ("s45", "es un tercer pizo sin asensor en origen", {"locations.origin.floor":3,"locations.origin.elevator":False}),
        ("s46", "enel destino ai asensor", {"locations.destination.elevator":True}),
        ("s47", "aca entra el camión pero aya queda lejitos", {"locations.origin.truck_access":True,"locations.destination.access_observation":"queda lejitos"}, "¿Cómo son los accesos?"),
        ("s48", "primero sí, segundo no", {"locations.origin.elevator":True,"locations.destination.elevator":False}, "¿Hay ascensor en ambos lugares?"),
        ("s49", "solo en el segundo", {"locations.origin.truck_access":False,"locations.destination.truck_access":True}, "¿El camión entra en ambos lugares?"),
        ("s50", "no era ahí", {}, "¿Confirmas que el destino es Barranco?"),
        ("s51", "la refrigeradora pesa 80 kilos y llevo 10 cajas", {"load":"refrigeradora 80 kilos 10 cajas"}, "", {"locations.origin.floor":80,"locations.destination.floor":10}),
        ("s52", "dos toneladas de mercadería", {"load":"dos toneladas mercaderia"}, "", {"locations.origin.carry_distance_m":2000,"locations.destination.carry_distance_m":2000}),
        ("s53", "el ascensor soporta 500 kg", {"load":"ascensor soporta 500 kg"}, "", {"locations.origin.floor":500,"locations.destination.floor":500}),
        ("s54", "llevo 3 camas del piso 8", {"load":"3 camas","locations.origin.floor":8}, "¿Qué llevas y de qué piso sale?", {"locations.origin.floor":3}),
        ("s55", "en origen 2do con ascensor, destino 5to; el camión queda lejos allá", {"locations.origin.floor":2,"locations.origin.elevator":True,"locations.destination.floor":5,"locations.destination.access_observation":"camion queda lejos"}),
        ("s56", "La Molina es origen, no destino", {"locations.origin.district":"La Molina"}, "", {}, [], True),
        ("s57", "sí, ambos tienen escaleras nomás", {"locations.origin.elevator":False,"locations.destination.elevator":False}, "¿Tienen ascensor en los dos?"),
        ("s58", "en uno sí", {}, "¿Hay ascensor en ambos?", {}, ["elevator"]),
        ("s59", "queda como a media cuadra en la llegada", {"locations.destination.access_observation":"media cuadra"}, "", {"locations.destination.carry_distance_m":50}),
        ("s60", "Quiero reservar ya", {}),
    ]
    for row in synthetic:
        case_id, message, expected, *tail = row
        question = tail[0] if len(tail) > 0 else ""
        forbidden = tail[1] if len(tail) > 1 else {}
        ambiguities = tail[2] if len(tail) > 2 else []
        correction = tail[3] if len(tail) > 3 else False
        cases.append(_case(case_id, message, expected, question=question,
                           forbidden=forbidden, ambiguities=ambiguities,
                           correction=correction))
    return cases
