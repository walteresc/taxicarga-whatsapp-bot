import re


def effective_load_detail(lead):
    """Canonical read API while legacy lista_objetos remains persisted."""
    detail = " ".join((lead.lista_objetos or "").split()).strip(" .")
    if not detail:
        return ""
    cleaned = re.sub(r"^(?:tengo|llevo|son)\s+", "", detail, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bunas?\s+(\d+)\s+cajas\b", r"aprox. \1 cajas", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:una|un)\s+(?=[a-záéíóúñ])", "", cleaned, flags=re.IGNORECASE)
    return cleaned[:1].upper() + cleaned[1:] if cleaned else detail
