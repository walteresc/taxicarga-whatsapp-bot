import re

from django.db.models import F, Value
from django.db.models.functions import Replace


PHONE_FORMATTING_CHARS = ("+", " ", "-", "(", ")", ".")


def normalize_phone_identity(value):
    """Digits-only phone identity; preserves normalized synthetic test identifiers."""
    raw = str(value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if digits and not re.search(r"[A-Za-z]", raw):
        return digits
    for character in PHONE_FORMATTING_CHARS:
        raw = raw.replace(character, "")
    return raw.lower()


def phone_to_e164(value):
    identity = normalize_phone_identity(value)
    return f"+{identity}" if identity.isdigit() else identity


def phone_for_meta(value):
    return normalize_phone_identity(value)


def with_phone_identity(queryset, *, alias="_phone_identity"):
    expression = F("telefono")
    for character in PHONE_FORMATTING_CHARS:
        expression = Replace(expression, Value(character), Value(""))
    return queryset.annotate(**{alias: expression})
