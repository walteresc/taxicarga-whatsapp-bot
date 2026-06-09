import hashlib
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.ia.models import EjemploConversacion


MESSAGE_RE = re.compile(
    r"^\[(?P<time>.+?),\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\]\s*"
    r"(?P<author>[^:]+):\s?(?P<text>.*)$"
)
CHAT_RE = re.compile(r"^\s*(?:cliente|cleinte)\s*(?P<number>\d+)\s*$", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?51[\s-]*)?9(?:[\s-]*\d){8}(?!\d)")
DOCUMENT_RE = re.compile(r"(?<!\d)\d{8,11}(?!\d)")
ADDRESS_RE = re.compile(
    r"\b(?:av\.?|avenida|jr\.?|jiron|jirón|calle|pasaje|mz\.?|manzana|"
    r"lote|urb\.?|urbanizacion|urbanización|direccion|dirección)\b",
    re.IGNORECASE,
)
NAME_RE = re.compile(
    r"\b(?:me llamo|mi nombre es|soy)\s+[A-Za-zÁÉÍÓÚÑáéíóúñ ]{3,}",
    re.IGNORECASE,
)


class Command(BaseCommand):
    help = "Importa ejemplos anonimizados desde exportaciones de WhatsApp."

    def add_arguments(self, parser):
        parser.add_argument("chat_path", help="Archivo TXT exportado o concatenado.")
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Elimina ejemplos importados previamente.",
        )

    def handle(self, *args, **options):
        path = Path(options["chat_path"])
        if not path.exists():
            raise CommandError(f"No existe el archivo: {path}")

        if options["clear"]:
            EjemploConversacion.objects.filter(fuente="whatsapp_export").delete()

        examples = []
        for chat_ref, turn, client_text, business_text in _iter_examples(path):
            client_redacted, client_review = _anonymize(client_text)
            business_redacted, business_review = _anonymize(business_text)
            if not client_redacted or not business_redacted:
                continue
            examples.append(
                EjemploConversacion(
                    fuente="whatsapp_export",
                    referencia_chat=chat_ref,
                    turno=turn,
                    mensaje_cliente=client_redacted,
                    respuesta_negocio=business_redacted,
                    etiquetas=_labels(client_redacted, business_redacted),
                    requiere_revision=client_review or business_review,
                )
            )

        with transaction.atomic():
            EjemploConversacion.objects.bulk_create(
                examples,
                batch_size=500,
                ignore_conflicts=True,
            )

        total = EjemploConversacion.objects.filter(fuente="whatsapp_export").count()
        review = EjemploConversacion.objects.filter(
            fuente="whatsapp_export",
            requiere_revision=True,
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Chats procesados localmente. Ejemplos: {total}. "
                f"Pendientes de revision: {review}."
            )
        )
        self.stdout.write(
            "Anonimizacion aplicada: telefonos, correos, documentos y enlaces."
        )


def _iter_examples(path):
    chats = _parse_messages(path)
    for chat_index, messages in enumerate(chats, start=1):
        source = "\n".join(message["raw"] for message in messages)
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
        chat_ref = f"chat_{chat_index:03d}_{digest}"
        client_parts = []
        business_parts = []
        turn = 0

        for message in messages:
            if message["business"]:
                if client_parts:
                    business_parts.append(message["text"])
            else:
                if client_parts and business_parts:
                    turn += 1
                    yield (
                        chat_ref,
                        turn,
                        "\n".join(client_parts),
                        "\n".join(business_parts),
                    )
                    client_parts = []
                    business_parts = []
                client_parts.append(message["text"])

        if client_parts and business_parts:
            turn += 1
            yield chat_ref, turn, "\n".join(client_parts), "\n".join(business_parts)


def _parse_messages(path):
    chats = []
    messages = []
    current = None
    with path.open(encoding="utf-8", errors="replace") as chat_file:
        for raw_line in chat_file:
            line = _repair_text(raw_line.rstrip("\n"))
            if CHAT_RE.match(line):
                if current:
                    messages.append(current)
                    current = None
                if messages:
                    chats.append(messages)
                    messages = []
                continue

            match = MESSAGE_RE.match(line)
            if match:
                if current:
                    messages.append(current)
                author = match.group("author").strip()
                current = {
                    "business": "lima express" in author.lower(),
                    "text": match.group("text").strip(),
                    "raw": line,
                }
            elif current:
                current["text"] += "\n" + line
                current["raw"] += "\n" + line

    if current:
        messages.append(current)
    if messages:
        chats.append(messages)
    return chats


def _anonymize(text):
    cleaned = _repair_text(text)
    cleaned = EMAIL_RE.sub("[CORREO]", cleaned)
    cleaned = URL_RE.sub("[ENLACE]", cleaned)
    cleaned = PHONE_RE.sub("[TELEFONO]", cleaned)
    cleaned = DOCUMENT_RE.sub("[DOCUMENTO]", cleaned)
    needs_review = bool(ADDRESS_RE.search(cleaned) or NAME_RE.search(cleaned))
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, needs_review


def _labels(client_text, business_text):
    combined = f"{client_text}\n{business_text}".lower()
    rules = {
        "saludo": ["hola", "buenos dias", "buenas tardes"],
        "ruta": ["origen", "destino", "distrito", "de que zona", "a que zona"],
        "objetos": ["lista", "foto", "cama", "refrigeradora", "mueble", "cajas"],
        "acceso": ["piso", "ascensor", "escalera", "puerta"],
        "embalaje": ["embal"],
        "desarmado": ["desarm", "armado"],
        "precio": ["precio", "costo", "s/.", "soles", "cotiza"],
        "reserva": ["reserv", "dni", "direccion exacta", "fecha", "hora"],
        "seguimiento": ["seguimos", "confirma", "decidio", "decidió"],
    }
    return [
        label
        for label, keywords in rules.items()
        if any(keyword in combined for keyword in keywords)
    ]


def _repair_text(value):
    repaired = value
    for _ in range(2):
        if "Ã" not in repaired and "Â" not in repaired and "ð" not in repaired:
            break
        try:
            repaired = repaired.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
    return repaired
