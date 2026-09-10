"""Búsqueda en el conocimiento de la empresa (`DocumentoConocimiento`).

Búsqueda simple por palabras (icontains sobre título + contenido). Si el corpus
crece, cambiar a full-text de Postgres — este es el único lugar a tocar.
"""
import re

from django.db.models import Q

from .models import DocumentoConocimiento

_TOKEN = re.compile(r"[a-záéíóúñ0-9]{3,}", re.IGNORECASE)


def buscar(consulta, *, incluir_internos, categoria=None, limite=4):
    qs = DocumentoConocimiento.objects.filter(activo=True)
    if not incluir_internos:
        qs = qs.filter(visibilidad=DocumentoConocimiento.VIS_PUBLICO)
    if categoria:
        qs = qs.filter(categoria=categoria)

    tokens = _TOKEN.findall(consulta or "")[:8]
    if tokens:
        cond = Q()
        for t in tokens:
            cond |= Q(titulo__icontains=t) | Q(contenido__icontains=t)
        qs = qs.filter(cond)
    elif not categoria:
        # sin consulta ni categoría: los de empresa (visión general)
        qs = qs.filter(categoria=DocumentoConocimiento.CAT_EMPRESA)

    return list(qs.order_by("categoria", "titulo")[:limite])
