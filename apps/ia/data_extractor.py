import re
import unicodedata
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone


STOP_WORDS = {
    "con",
    "tengo",
    "llevo",
    "incluye",
    "piso",
    "sin",
    "ascensor",
    "para",
    "el",
    "la",
    "los",
    "las",
    "y",
}

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}

LIMA_DISTRICTS = [
    "San Juan De Lurigancho",
    "San Juan De Miraflores",
    "San Martin De Porres",
    "Villa Maria Del Triunfo",
    "Villa El Salvador",
    "Magdalena Del Mar",
    "Santiago De Surco",
    "Pueblo Libre",
    "Jesus Maria",
    "La Victoria",
    "La Molina",
    "Los Olivos",
    "San Borja",
    "San Isidro",
    "San Miguel",
    "Santa Anita",
    "Puente Piedra",
    "El Agustino",
    "Independencia",
    "Miraflores",
    "Chorrillos",
    "Surquillo",
    "Barranco",
    "Carabayllo",
    "Cercado De Lima",
    "Breña",
    "Comas",
    "Lince",
    "Rimac",
    "Ate",
    "Surco",
]


def extract_lead_data(message):
    text = message.strip()
    lowered = text.lower()
    data = {}

    name = _extract_name(text)
    if name:
        data["cliente_nombre"] = name

    service_type = _extract_service_type(lowered)
    if service_type:
        data["tipo_servicio"] = service_type

    origin, destination = _extract_route(lowered)
    if origin:
        data["distrito_origen"] = origin
    if destination:
        data["distrito_destino"] = destination

    floor_origin, floor_destination = _extract_floors(lowered)
    if floor_origin is not None:
        data["piso_origen"] = floor_origin
    if floor_destination is not None:
        data["piso_destino"] = floor_destination

    elevator_origin, elevator_destination = _extract_elevators(lowered)
    if elevator_origin is not None:
        data["ascensor_origen"] = elevator_origin
    if elevator_destination is not None:
        data["ascensor_destino"] = elevator_destination

    if (
        ("ambos" in lowered or "los dos" in lowered)
        and "camion" in lowered
        and any(term in lowered for term in ("puerta", "puede acercarse", "llega"))
    ):
        reaches = not any(term in lowered for term in ("no llega", "no entra", "lejos"))
        data["camion_llega_origen"] = reaches
        data["camion_llega_destino"] = reaches

    service_date = _extract_date(lowered)
    if service_date:
        data["fecha_servicio"] = service_date

    schedule = _extract_schedule(lowered)
    if schedule:
        data["horario_servicio"] = schedule

    if _has_object_list(lowered):
        data["lista_objetos"] = _extract_load_detail(text) or text

    heavy_items = _extract_heavy_items(lowered)
    if heavy_items:
        data["objetos_pesados"] = heavy_items

    modality = _extract_service_modality(lowered)
    if modality:
        data["modalidad_servicio"] = modality

    personnel = _extract_loading_personnel(lowered)
    if personnel is not None:
        data["incluye_personal_carga"] = personnel
        if personnel is False:
            data["cantidad_operarios"] = 0

    operator_count = _extract_operator_count(lowered)
    if operator_count is not None:
        data["incluye_personal_carga"] = operator_count > 0
        data["cantidad_operarios"] = operator_count

    disassembly = _extract_disassembly(lowered)
    if disassembly is not None:
        data["requiere_desarmado"] = disassembly

    assembly = _extract_assembly(lowered)
    if assembly is not None:
        data["requiere_armado"] = assembly

    weight = _extract_decimal_unit(lowered, ("kg", "kilos", "kilogramos"))
    if weight is not None:
        data["peso_carga_kg"] = weight

    volume = _extract_decimal_unit(lowered, ("m3", "metros cubicos", "metro cubico"))
    if volume is not None:
        data["volumen_carga_m3"] = volume

    dni = re.search(r"\b(?:dni\s*)?(\d{8})\b", lowered)
    if dni:
        data["dni_reserva"] = dni.group(1)

    return data


def has_explicit_floor_reference(message):
    text = _canonical_text(message)
    if re.search(r"\b(?:piso|planta|nivel)\b", text):
        return True
    return bool(re.search(
        r"\b(?:\d{1,2}\s*(?:ero|er|ro|do|to|avo)|primer|primero|segundo|"
        r"tercer|tercero|cuarto|quinto|sexto|septimo|octavo|noveno|decimo)\b",
        text,
    ))


def extract_route_locations(message):
    normalized = _canonical_text(message)
    matches = []
    candidates = sorted(LIMA_DISTRICTS, key=len, reverse=True)
    for district in candidates:
        canonical = _canonical_text(district)
        for match in re.finditer(rf"\b{re.escape(canonical)}\b", normalized):
            matches.append((match.start(), match.end(), normalize_district(district)))
    matches.sort(key=lambda item: item[0])
    deduplicated = []
    for match in matches:
        if any(start <= match[0] < end for start, end, _district in deduplicated):
            continue
        deduplicated.append(match)
    if len(deduplicated) < 2:
        return []

    locations = []
    for index, (start, _end, district) in enumerate(deduplicated):
        segment_end = deduplicated[index + 1][0] if index + 1 < len(deduplicated) else len(normalized)
        segment = normalized[start:segment_end]
        floor = _extract_single_floor(segment)
        elevator = None
        if "sin ascensor" in segment or "no hay ascensor" in segment or "escalera" in segment:
            elevator = False
        elif "con ascensor" in segment or "hay ascensor" in segment or "elevador" in segment:
            elevator = True
        locations.append({
            "tipo": "origen" if index == 0 else ("destino" if index == len(deduplicated) - 1 else "parada"),
            "distrito": district,
            "piso": floor,
            "ascensor": elevator,
        })
    return locations


def _extract_name(text):
    patterns = [
        r"\bme llamo\s+([A-Za-z ]{2,60})",
        r"\bsoy\s+([A-Za-z ]{2,60})",
        r"\bmi nombre es\s+([A-Za-z ]{2,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_name(match.group(1))
    return None


def _extract_service_type(text):
    if any(word in text for word in ["mudanza", "mudar", "departamento", "casa"]):
        return "mudanza"
    if "traslado pequeno" in text or "traslado pequeño" in text:
        return "traslado pequeno"
    if any(word in text for word in ["oficina", "corporativo", "empresa"]):
        return "oficina"
    if (
        re.search(r"\b(?:carga|flete|transporte)\b", text)
        and not any(
            term in text
            for term in [
                "personal para cargar",
                "ayudante para cargar",
                "carga y descarga",
            ]
        )
    ):
        return "carga"
    return None


def _extract_route(text):
    patterns = [
        r"\b(?:de|desde|origen)\s+(.+?)\s+(?:a|hacia|hasta|destino)\s+(.+)",
        r"\b(?:se\s+)?(?:recoge|recogen|sale)\s+de\s+(.+?)\s+(?:y\s+)?(?:va|llega)\s+a\s+(.+)",
        r"\bsale\s+(.+?)\s+y\s+va\s+a\s+(.+)",  # "sale surco y va a miraflores"
    ]
    match = None
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            break
    if not match:
        return None, None
    origin = match.group(1)
    destination = match.group(2)
    if "piso" in origin or (
        "piso" in destination
        and not any(district.lower() in destination.lower() for district in LIMA_DISTRICTS)
    ):
        return None, None
    return normalize_district(origin), normalize_district(destination)


def _extract_floors(text):
    origin = _extract_labeled_floor(text, ["origen", "recojo", "recogida", "salida"])
    destination = _extract_labeled_floor(text, ["destino", "llegada", "entrega"])
    pair = re.search(
        r"\b(\d+)\s*(?:ero|er|ro|do|to)?(?:\s+[a-z]*piso)?\s+"
        r"(?:a|al|hasta)\s+"
        r"(\d+)\s*(?:ero|er|ro|do|to)?(?:\s+[a-z]*piso)?\b",
        text,
    )
    if pair:
        return int(pair.group(1)), int(pair.group(2))
    floors = [
        int(before or after)
        for before, after in re.findall(
            r"(?:(\d+)\s*(?:er|to|do|ro)?\s*piso|piso\s*(\d+))",
            text,
        )
    ]
    if origin is None and floors:
        origin = floors[0]
    if destination is None and len(floors) > 1:
        destination = floors[1]
    return origin, destination


def _extract_labeled_floor(text, labels):
    floor_words = {
        "primer": 1, "primero": 1, "segundo": 2, "tercer": 3, "tercero": 3,
        "cuarto": 4, "quinto": 5, "sexto": 6,
    }
    for label in labels:
        patterns = [
            rf"{label}\D{{0,20}}(\d+)\s*(?:er|to|do|ro)?\s*piso",
            rf"(\d+)\s*(?:er|to|do|ro)?\s*piso\D{{0,20}}{label}",
            rf"{label}\D{{0,20}}piso\s*(\d+)",
            rf"piso\s*(\d+)\D{{0,20}}{label}",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))
        word_match = re.search(
            rf"{label}.{{0,20}}\b({'|'.join(floor_words)})\s+piso",
            text,
        )
        if word_match:
            return floor_words[word_match.group(1)]
    return None


def _extract_elevators(text):
    paired = re.search(
        r"(?:origen|sale|surco).{0,45}?(con|sin) ascensor"
        r".{0,60}?(?:destino|llega|miraflores|san isidro).{0,45}?(con|sin) ascensor",
        text,
    )
    if paired:
        return paired.group(1) == "con", paired.group(2) == "con"
    origin = _extract_labeled_elevator(text, ["origen", "recojo", "recogida", "salida"])
    destination = _extract_labeled_elevator(text, ["destino", "llegada", "entrega"])
    if "sin ascensor" in text:
        origin = False if origin is None else origin
        destination = False if destination is None else destination
    elif "con ascensor" in text or "hay ascensor" in text or "tiene ascensor" in text:
        origin = True if origin is None else origin
        destination = True if destination is None else destination
    return origin, destination


def _extract_labeled_elevator(text, labels):
    for label in labels:
        window_pattern = rf"(.{{0,25}}{label}.{{0,25}}|{label}.{{0,25}})"
        for match in re.finditer(window_pattern, text):
            window = match.group(0)
            if "sin ascensor" in window or "no tiene ascensor" in window:
                return False
            if "con ascensor" in window or "hay ascensor" in window or "tiene ascensor" in window:
                return True
    return None


def _extract_date(text):
    today = timezone.localdate()
    if "hoy" in text:
        return today
    if "manana" in text or "mañana" in text:
        return today + timedelta(days=1)
    for weekday, weekday_number in WEEKDAYS.items():
        if re.search(rf"\b{weekday}\b", text):
            days_ahead = (weekday_number - today.weekday()) % 7
            return today + timedelta(days=days_ahead)
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3) or today.year)
        if year < 100:
            year += 2000
        return today.replace(year=year, month=month, day=day)
    match = re.search(r"\b(\d{1,2})\s+de\s+([a-z]+)\b", text)
    if match and match.group(2) in MONTHS:
        return today.replace(day=int(match.group(1)), month=MONTHS[match.group(2)])
    return None


def _extract_schedule(text):
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text)
    if match:
        minute = match.group(2) or "00"
        return f"{match.group(1)}:{minute} {match.group(3)}"
    match = re.search(r"\b(?:a las|tipo|hora)\s+(\d{1,2})(?::(\d{2}))?\b", text)
    if match:
        minute = match.group(2) or "00"
        return f"{match.group(1)}:{minute}"
    if "manana" in text or "mañana" in text:
        return "manana"
    if "tarde" in text:
        return "tarde"
    if "noche" in text:
        return "noche"
    return None


def _has_object_list(text):
    object_words = [
        "cama",
        "refrigeradora",
        "mueble",
        "sofa",
        "mesa",
        "sillas",
        "cajas",
        "lavadora",
        "ropero",
        "escritorio",
        "colchon",
    ]
    return any(word in text for word in object_words)


def _extract_heavy_items(text):
    heavy_words = [
        "refrigeradora de 2 puertas",
        "refri de 2 puertas",
        "caja fuerte",
        "piano",
        "ropero",
        "comoda",
        "aparador",
        "vitrina",
        "lavadora",
    ]
    found = [word for word in heavy_words if word in text]
    return ", ".join(found)


def _extract_service_modality(text):
    lowered = text.lower()
    if any(term in lowered for term in ["embalaje full", "embalaje total", "embalar todo", "full"]):
        return "embalaje full"
    if any(
        term in lowered
        for term in [
            "embalaje de muebles y artefactos",
            "embalaje muebles y artefactos",
            "embalaje completo",
            "muebles y artefactos",
        ]
    ):
        return "embalaje de muebles y artefactos"
    if any(
        term in lowered
        for term in [
            "embalaje basico", "embalaje básico",
            "algunas cosas", "solo lo fragil", "solo lo más frágil",
            "cosas delicadas", "solo algunas", "solo algo",
            "unas cuantas", "lo mas fragil", "lo más frágil",
            "algunas", "pocas cosas",
        ]
    ):
        return "embalaje basico"
    if any(
        term in lowered
        for term in [
            "sin embalaje",
            "no necesito embalaje",
            "no requiero embalaje",
            "no quiero embalaje",
            "solo transporte",
            "yo lo embalo",
            "yo mismo lo embalo",
            "sin problema",
            "no gracias",
        ]
    ):
        return "sin embalaje"
    if "con embalaje" in lowered or "necesito embalaje" in lowered:
        return "embalaje basico"
    return None


def _extract_loading_personnel(text):
    if any(
        term in text
        for term in [
            "con personal",
            "con ayudante",
            "con ayudantes",
            "con operario",
            "con operarios",
            "para cargar",
            "carga y descarga",
        ]
    ):
        return True
    if any(
        term in text
        for term in [
            "solo transporte",
            "solo trans porte",
            "solo trasnporte",
            "solo traslado",
            "sin personal",
            "sin ayudante",
            "yo cargo",
            "nosotros cargamos",
            "solo vehiculo",
            "solo vehiculo",
            "solo el camion",
            "solo camion",
            "solo la movilidad",
            "solo movilidad",
        ]
    ):
        return False
    if re.search(r"\bsolo\s+(?:tr[ea]ns?por?te?|trasnporte|movilidad|camion|vehiculo)\b", text):
        return False
    if re.search(r"\bsin\s*(?:ayudante|operario|cargador|mozos?)\b", text):
        return False
    if re.search(r"\bno\s+(?:necesito|requiero|quiero)\s+(?:personal|cargador|ayudante|operario)", text):
        return False
    if re.search(r"\b(?:nosotros|yo)\s+(?:mism[oa]s?|solos?)\s+(?:cargamos|cargo|hacemos|hago)\b", text):
        return False
    return None


def _extract_disassembly(text):
    if any(
        term in text
        for term in [
            "desarmado y armado",
            "desarmar y armar",
            "desarme y armado",
            "hay que desarmar",
            "necesito desarmar",
            "quiero desarmar",
        ]
    ):
        return True
    if any(term in text for term in ["sin desarmado", "no desarmar", "no necesito desarmado"]):
        return False
    return None


def _extract_assembly(text):
    if any(term in text for term in ["desarmado y armado", "desarmar y armar", "armado de muebles", "necesito armado", "quiero armado"]):
        return True
    if any(term in text for term in ["sin armado", "no armar", "no necesito armado"]):
        return False
    return None


def _extract_operator_count(text):
    match = re.search(
        r"\b(\d+|un|uno|dos|tres|cuatro|cinco|seis)\s+"
        r"(?:ayudantes?|operarios?|cargadores?|mozos?)\b",
        text,
    )
    if not match:
        return None
    numbers = {"un": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6}
    return numbers.get(match.group(1), int(match.group(1)) if match.group(1).isdigit() else None)


def _extract_load_detail(text):
    patterns = [
        r"\b(?:tengo|llevo|llevar[ée]?|traslado|transporto|son)\s+(.+)",
        r"\b(?:carga|cosas|objetos)\s*[:=-]\s*(.+)",
    ]
    detail = ""
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            detail = match.group(1)
            break
    if not detail:
        return ""
    detail = re.split(
        r"[.;]|\b(?:origen|destino|recojo|sale de|llega a|para el|mañana|manana|a las|nosotros cargamos)\b",
        detail,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return detail.strip(" ,.-")


def _extract_single_floor(text):
    numeric = re.search(
        r"\b(?:piso|planta|nivel)\s*(\d{1,2})(?:ro|do|to|er|avo)?\b|"
        r"\b(\d{1,2})(?:ro|do|to|er|avo)?\s*(?:piso|planta|nivel)\b",
        text,
    )
    if numeric:
        return int(numeric.group(1) or numeric.group(2))
    words = {
        "primer": 1, "primero": 1, "segundo": 2, "tercer": 3, "tercero": 3,
        "cuarto": 4, "quinto": 5, "sexto": 6, "septimo": 7, "octavo": 8,
        "noveno": 9, "decimo": 10,
    }
    for word, number in words.items():
        if re.search(rf"\b{word}\s+(?:piso|planta|nivel)\b", text):
            return number
    if "puerta a calle" in text or "primer nivel" in text:
        return 1
    return None


def _canonical_text(value):
    normalized = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _extract_decimal_unit(text, units):
    unit_pattern = "|".join(re.escape(unit) for unit in units)
    match = re.search(rf"\b(\d+(?:[.,]\d+)?)\s*(?:{unit_pattern})\b", text)
    if not match:
        return None
    return Decimal(match.group(1).replace(",", "."))


def _clean_place(value):
    words = []
    for raw_word in re.split(r"\s+", value.strip(" .,")):
        word = raw_word.strip(" .,")
        if not word or word in STOP_WORDS or re.search(r"\d", word):
            break
        words.append(word)
        if len(words) >= 3:
            break
    return " ".join(words).title()


def normalize_district(value):
    cleaned = re.sub(
        r"^(?:de|desde|hacia|a|al|en|se\s+recoge(?:n)?\s+de|va\s+a)\s+",
        "",
        str(value or "").strip(" .,"),
        flags=re.IGNORECASE,
    )
    lowered = cleaned.lower()
    for district in LIMA_DISTRICTS:
        if district.lower() in lowered:
            return district
    return _clean_place(cleaned)


def _clean_name(value):
    stop = re.search(r"\b(?:y|quiero|necesito|busco|para|de|desde|con)\b", value, flags=re.IGNORECASE)
    if stop:
        value = value[: stop.start()]
    return " ".join(value.strip(" .,").title().split()[:4])
