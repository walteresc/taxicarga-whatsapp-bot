"""Capacidad: consultar el conocimiento de la empresa y del rubro."""
from apps.agente.registro import EFECTO_LECTURA, capacidad

_CATEGORIAS = ["empresa", "servicios", "logistica", "precios", "politicas",
               "procedimientos", "glosario"]


@capacidad("consultar_conocimiento",
           perfiles=["asesor", "transportista", "cliente", "sistema"],
           efecto=EFECTO_LECTURA, params={
               "tema": {"description": "Qué querés saber (palabras clave)."},
               "categoria": {"enum": _CATEGORIAS,
                             "description": "Opcional: acotar a una categoría."},
           })
def consultar_conocimiento(principal, tema="", categoria=None):
    """Busca en la información de la empresa (servicios, cobertura, precios,
    políticas, procedimientos, glosario). Usalo antes de responder sobre cómo
    funciona Lima Express — no supongas."""
    from apps.agente.conocimiento import buscar

    docs = buscar(tema, incluir_internos=principal.es_interno,
                  categoria=categoria if categoria in _CATEGORIAS else None)
    if not docs:
        return {"encontrado": False,
                "nota": "No hay un documento cargado sobre eso. Respondé solo lo "
                        "que sepas con certeza o derivá a un asesor."}
    return {
        "encontrado": True,
        "documentos": [
            {"titulo": d.titulo, "categoria": d.categoria, "contenido": d.contenido}
            for d in docs
        ],
    }
