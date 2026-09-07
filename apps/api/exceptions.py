"""Manejador de excepciones uniforme para la API v2.

Toda respuesta de error tiene la misma forma:

    {"error": "<mensaje legible>", "fields": {"<campo>": ["<msg>", ...]}}

- 400 de validación  -> error genérico + `fields` con el detalle por campo.
- 401 / 403 / 404 / 409 / 5xx -> `error` con el mensaje, `fields` vacío.

Se activa vía REST_FRAMEWORK["EXCEPTION_HANDLER"] en settings.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler


def api_exception_handler(exc, context):
    if isinstance(exc, IntegrityError):
        return Response(
            {"error": "El registro entra en conflicto con otro existente.", "fields": {}},
            status=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, "message_dict"):
            fields = {k: list(v) for k, v in exc.message_dict.items()}
            return Response(
                {"error": "Revisa los datos del formulario.", "fields": fields},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"error": exc.messages[0] if exc.messages else "Datos inválidos.", "fields": {}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    response = drf_default_handler(exc, context)
    if response is None:
        return None

    data = response.data
    fields = {}
    error = "No se pudo completar la operación."

    if isinstance(data, dict):
        if "detail" in data and len(data) == 1:
            error = str(data["detail"])
        else:
            fields = {k: (v if isinstance(v, list) else [str(v)]) for k, v in data.items()}
            error = "Revisa los datos del formulario."
            non_field = fields.pop("non_field_errors", None)
            if non_field:
                error = non_field[0]
    elif isinstance(data, list):
        error = data[0] if data else error

    response.data = {"error": error, "fields": fields}
    return response
