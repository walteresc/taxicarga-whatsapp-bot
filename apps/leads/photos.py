"""Fotos de la carga (hasta 5) al cotizar — apps.leads.models.LeadFoto.

Los endpoints de cotización de invitado y del portal cliente aceptaban solo
JSON (origin/destination/cargo son objetos anidados). Para no reescribir
todo el body como multipart, cuando el cliente adjunta fotos se manda
multipart/form-data con un campo `data` = el mismo JSON de siempre
(stringificado) + `photo1`..`photo5` = los archivos. Sin fotos, se sigue
mandando JSON plano tal cual — `parse_request_body` soporta ambos.
"""
import json

from django.core.exceptions import ValidationError

from .models import LeadFoto

MAX_FOTOS = 5


def parse_request_body(request):
    """(dict de datos, lista de archivos) — ver docstring del módulo."""
    content_type = request.content_type or ""
    if "multipart/form-data" not in content_type:
        return (request.data or {}), []

    raw = request.data.get("data") or "{}"
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        raise ValidationError("Datos inválidos.")
    fotos = [
        request.data[key] for key in sorted(request.data.keys())
        if key.startswith("photo") and request.data.get(key)
    ][:MAX_FOTOS]
    return data, fotos


def save_lead_photos(lead, fotos):
    if not fotos:
        return
    LeadFoto.objects.bulk_create([
        LeadFoto(lead=lead, imagen=archivo, orden=index)
        for index, archivo in enumerate(fotos[:MAX_FOTOS])
    ])
