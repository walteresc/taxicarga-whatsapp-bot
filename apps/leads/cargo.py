def effective_load_detail(lead):
    """Canonical read API while legacy lista_objetos remains persisted."""
    return " ".join((lead.lista_objetos or "").split())
