import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cotizador.models import ServicioHistorico


INSERT_PREFIX = "INSERT INTO `carga`"
MIN_TRAINING_PRICE = Decimal("50.00")
MAX_TRAINING_PRICE = Decimal("10000.00")
DISTRICTS = [
    "San Juan de Lurigancho",
    "San Juan de Miraflores",
    "Santiago de Surco",
    "Villa Maria del Triunfo",
    "Villa El Salvador",
    "Magdalena del Mar",
    "Jesus Maria",
    "Pueblo Libre",
    "San Martin de Porres",
    "La Victoria",
    "La Molina",
    "Los Olivos",
    "San Borja",
    "San Isidro",
    "San Miguel",
    "Santa Anita",
    "Puente Piedra",
    "Chorrillos",
    "Miraflores",
    "Barranco",
    "Surquillo",
    "Ate",
    "Breña",
    "Carabayllo",
    "Comas",
    "El Agustino",
    "Independencia",
    "Lince",
    "Rimac",
    "Cercado de Lima",
]


class Command(BaseCommand):
    help = "Importa historicos operativos desde un dump SQL de Wally sin datos personales."

    def add_arguments(self, parser):
        parser.add_argument("sql_path", help="Ruta al dump SQL de Wally.")
        parser.add_argument(
            "--clear-wally",
            action="store_true",
            help="Elimina historicos importados previamente desde Wally.",
        )

    def handle(self, *args, **options):
        sql_path = Path(options["sql_path"])
        if not sql_path.exists():
            raise CommandError(f"No existe el archivo: {sql_path}")

        if options["clear_wally"]:
            ServicioHistorico.objects.filter(fuente="wally").delete()

        existing = set()
        if not options["clear_wally"]:
            existing = set(
                ServicioHistorico.objects.filter(fuente="wally").values_list(
                    "referencia_externa",
                    flat=True,
                )
            )

        pending = []
        skipped = reserved = duplicates = 0
        for columns, row in _iter_carga_rows(sql_path):
            record = dict(zip(columns, row))
            defaults = _historical_defaults(record)
            if defaults is None:
                skipped += 1
                continue

            reference = str(record["codcarga"])
            if reference in existing:
                duplicates += 1
                continue
            existing.add(reference)
            pending.append(
                ServicioHistorico(
                    fuente="wally",
                    referencia_externa=reference,
                    **defaults,
                )
            )
            reserved += int(defaults["cerrado"])

        with transaction.atomic():
            ServicioHistorico.objects.bulk_create(pending, batch_size=1000)

        self.stdout.write(
            self.style.SUCCESS(
                "Importacion Wally lista. "
                f"Creados: {len(pending)}. Duplicados: {duplicates}. "
                f"Reservados nuevos: {reserved}. Omitidos: {skipped}."
            )
        )
        self.stdout.write(
            "Privacidad: no se importaron nombres, telefonos, correos, DNI ni usuarios."
        )


def _iter_carga_rows(path):
    statement = []
    collecting = False
    with path.open(encoding="utf-8", errors="replace") as sql_file:
        for line in sql_file:
            if line.startswith(INSERT_PREFIX):
                collecting = True
                statement = [line]
            elif collecting:
                statement.append(line)

            if collecting and line.rstrip().endswith(";"):
                text = "".join(statement)
                columns_match = re.search(r"\((.*?)\)\s+VALUES\s*", text, re.DOTALL)
                if columns_match:
                    columns = [
                        item.strip().strip("`")
                        for item in columns_match.group(1).split(",")
                    ]
                    values_text = text[columns_match.end() :].rstrip().rstrip(";")
                    for row in _parse_value_tuples(values_text):
                        if len(row) == len(columns):
                            yield columns, row
                collecting = False
                statement = []


def _parse_value_tuples(text):
    rows = []
    row = []
    token = []
    in_string = False
    escaped = False
    depth = 0

    for char in text:
        if in_string:
            if escaped:
                token.append({"n": "\n", "r": "\r", "t": "\t"}.get(char, char))
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "'":
                in_string = False
            else:
                token.append(char)
            continue

        if char == "'":
            in_string = True
        elif char == "(":
            depth += 1
            if depth == 1:
                row = []
                token = []
        elif char == "," and depth == 1:
            row.append(_convert_token("".join(token)))
            token = []
        elif char == ")":
            if depth == 1:
                row.append(_convert_token("".join(token)))
                rows.append(row)
                token = []
            depth -= 1
        elif depth == 1:
            token.append(char)
    return rows


def _convert_token(value):
    cleaned = value.strip()
    if cleaned.upper() == "NULL":
        return None
    return cleaned


def _historical_defaults(record):
    price = _decimal(record.get("montocarga"))
    date = _date(record.get("fechaserv")) or _date(record.get("fechareg"))
    if (
        not price
        or price < MIN_TRAINING_PRICE
        or price > MAX_TRAINING_PRICE
        or not date
    ):
        return None

    status = _clean(record.get("estadodecarga")).lower()
    description = _clean(record.get("descripcion"))
    origin_floor = _floor(record.get("pisorecojo"))
    destination_floor = _floor(record.get("pisoentrega"))
    origin_access = _clean(record.get("acceso1")) or _clean(record.get("pisorecojo"))
    destination_access = _clean(record.get("acceso2")) or _clean(record.get("pisoentrega"))
    origin_elevator = _elevator(origin_access)
    destination_elevator = _elevator(destination_access)
    modality = _service_modality(record, description)

    return {
        "fecha": date,
        "tipo_servicio": _service_type(record, description),
        "distrito_origen": _district(record.get("origen")),
        "distrito_destino": _district(record.get("destino")),
        "piso_origen": origin_floor,
        "piso_destino": destination_floor,
        "ascensor_origen": origin_elevator,
        "ascensor_destino": destination_elevator,
        "lista_objetos": description,
        "objetos_pesados": _heavy_items(description),
        "modalidad_servicio": modality,
        "requiere_desarmado": _mentions_disassembly(description),
        "acceso_origen": origin_access,
        "acceso_destino": destination_access,
        "camion_llega_origen": None,
        "camion_llega_destino": None,
        "camion_usado": _vehicle(record),
        "capacidad_camion": "",
        "ayudantes": (
            _integer(record.get("cantestiba"))
            if _integer(record.get("cantestiba")) is not None
            else 2
        ),
        "precio_cotizado": price,
        "precio_final": price if "reserv" in status else None,
        "cerrado": "reserv" in status,
        "observaciones": _operational_notes(record, description),
    }


def _clean(value):
    return str(value or "").strip()


def _date(value):
    text = _clean(value)
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%d%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _decimal(value):
    try:
        result = Decimal(_clean(value).replace(",", "."))
        return result if result > 0 else None
    except InvalidOperation:
        return None


def _integer(value):
    try:
        return int(float(_clean(value)))
    except (TypeError, ValueError):
        return None


def _district(address):
    text = _repair_text(_clean(address))
    lowered = text.lower()
    for district in DISTRICTS:
        if district.lower() in lowered:
            return district
    return text.split(",")[0].strip()[:120]


def _floor(value):
    text = _repair_text(_clean(value)).lower()
    floor_match = re.search(r"(\d+)", text)
    return int(floor_match.group(1)) if floor_match else None


def _elevator(value):
    text = _repair_text(_clean(value)).lower()
    if "ascensor" in text:
        return True
    if any(word in text for word in ["escalera", "ninguno", "sin ascensor"]):
        return False
    return None


def _service_type(record, description):
    combined = " ".join(
        [
            _clean(record.get("tiposervicio")),
            _clean(record.get("tipotransporte")),
            description,
        ]
    ).lower()
    if "oficina" in combined:
        return "oficina"
    if any(word in combined for word in ["mudanza", "cama", "colchon", "ropero"]):
        return "mudanza"
    return "carga"


def _service_modality(record, description):
    combined = " ".join(
        [
            _clean(record.get("tipoembalaje")),
            _clean(record.get("tiposervicio")),
            description,
        ]
    ).lower()
    if "completo" in combined:
        return "embalaje completo y traslado"
    if any(word in combined for word in ["embal", "proteger", "forrar"]):
        return "embalaje basico y traslado"
    return "solo traslado"


def _heavy_items(description):
    lowered = description.lower()
    items = [
        item
        for item in [
            "refrigeradora de 2 puertas",
            "refri de 2 puertas",
            "piano",
            "caja fuerte",
            "ropero",
            "comoda",
            "aparador",
            "lavadora",
        ]
        if item in lowered
    ]
    return ", ".join(items)


def _mentions_disassembly(description):
    lowered = description.lower()
    if any(word in lowered for word in ["desarm", "desmont"]):
        return True
    return None


def _vehicle(record):
    vehicle_id = _clean(record.get("codtipovehiculo1") or record.get("codtipovehiculo"))
    return f"vehiculo_wally_{vehicle_id}" if vehicle_id else ""


def _operational_notes(record, description):
    parts = [
        f"servicio={_clean(record.get('tiposervicio'))}",
        f"transporte={_clean(record.get('tipotransporte'))}",
        f"cargadores={_clean(record.get('tipocargadores'))}",
        f"embalaje={_clean(record.get('tipoembalaje'))}",
    ]
    lowered = description.lower()
    considerations = []
    if any(word in lowered for word in ["desarm", "desmont"]):
        considerations.append("desarmado")
    if any(word in lowered for word in ["armar", "armado", "montaje"]):
        considerations.append("armado")
    if "soga" in lowered:
        considerations.append("sogas")
    if "ascensor" in lowered:
        considerations.append("restriccion_ascensor")
    if any(word in lowered for word in ["camion no llega", "camión no llega", "lejos de la puerta"]):
        considerations.append("acarreo_adicional")
    if considerations:
        parts.append("consideraciones=" + ",".join(considerations))
    return "; ".join(part for part in parts if not part.endswith("="))


def _repair_text(value):
    repaired = value
    for _ in range(2):
        if "Ã" not in repaired:
            break
        try:
            repaired = repaired.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
    return repaired
