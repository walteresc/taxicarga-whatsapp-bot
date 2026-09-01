import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from apps.dashboard.permissions import role_required

from .models import Ayudante, Conductor


PERSONAL_ROLES = ("Administrador", "Supervisor", "Asesor de Ventas")


def _payload(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError as exc:
        raise ValidationError("JSON inválido.") from exc


def _validation_errors(exc):
    if hasattr(exc, "message_dict"):
        return {key: list(values) for key, values in exc.message_dict.items()}
    return {"general": list(exc.messages)}


def _pagination(request, queryset):
    try:
        page_size = min(max(int(request.GET.get("page_size", 20)), 1), 100)
    except (TypeError, ValueError):
        page_size = 20
    paginator = Paginator(queryset, page_size)
    page = paginator.get_page(request.GET.get("page", 1))
    return page, {
        "page": page.number,
        "page_size": page_size,
        "total": paginator.count,
        "pages": paginator.num_pages,
    }


def _filtered(request, queryset, fields):
    search = request.GET.get("search", "").strip()
    if search:
        query = Q()
        for field in fields:
            query |= Q(**{f"{field}__icontains": search})
        queryset = queryset.filter(query)
    status = request.GET.get("status", "all")
    if status == "active":
        queryset = queryset.filter(activo=True)
    elif status == "inactive":
        queryset = queryset.filter(activo=False)
    return queryset


def _conductor_json(item):
    return {
        "id": item.pk,
        "nombre": item.nombre,
        "dni": item.dni,
        "telefono": item.telefono,
        "numero_licencia": item.numero_licencia,
        "categoria_licencia": item.categoria_licencia,
        "fecha_vencimiento_licencia": (
            item.fecha_vencimiento_licencia.isoformat()
            if item.fecha_vencimiento_licencia else None
        ),
        "usuario": (
            {"id": item.usuario_id, "nombre": item.usuario.get_full_name() or item.usuario.username}
            if item.usuario_id else None
        ),
        "activo": item.activo,
        "observaciones": item.observaciones,
    }


def _ayudante_json(item):
    return {
        "id": item.pk,
        "nombre": item.nombre,
        "dni": item.dni,
        "telefono": item.telefono,
        "usuario": (
            {"id": item.usuario_id, "nombre": item.usuario.get_full_name() or item.usuario.username}
            if item.usuario_id else None
        ),
        "activo": item.activo,
        "observaciones": item.observaciones,
    }


def _save(instance, data, allowed_fields):
    for field in allowed_fields:
        if field in data:
            setattr(instance, field, data[field])
    instance.full_clean()
    instance.save()
    return instance


@login_required
@role_required(*PERSONAL_ROLES)
@require_http_methods(["GET", "POST"])
def conductores_api(request):
    if request.method == "GET":
        queryset = _filtered(
            request,
            Conductor.objects.select_related("usuario").order_by("nombre", "id"),
            ("nombre", "dni", "telefono", "numero_licencia"),
        )
        page, pagination = _pagination(request, queryset)
        return JsonResponse({"results": [_conductor_json(item) for item in page], **pagination})

    try:
        data = _payload(request)
        with transaction.atomic():
            item = _save(
                Conductor(),
                data,
                (
                    "nombre", "dni", "telefono", "numero_licencia",
                    "categoria_licencia", "fecha_vencimiento_licencia",
                    "activo", "observaciones",
                ),
            )
        return JsonResponse(_conductor_json(item), status=201)
    except ValidationError as exc:
        return JsonResponse({"errors": _validation_errors(exc)}, status=400)
    except IntegrityError:
        return JsonResponse({"errors": {"dni": ["Ya existe un conductor con este DNI."]}}, status=409)


@login_required
@role_required(*PERSONAL_ROLES)
@require_http_methods(["GET", "PUT", "PATCH"])
def conductor_api(request, pk):
    item = get_object_or_404(Conductor.objects.select_related("usuario"), pk=pk)
    if request.method == "GET":
        return JsonResponse(_conductor_json(item))
    try:
        data = _payload(request)
        with transaction.atomic():
            _save(
                item,
                data,
                (
                    "nombre", "dni", "telefono", "numero_licencia",
                    "categoria_licencia", "fecha_vencimiento_licencia",
                    "activo", "observaciones",
                ),
            )
        return JsonResponse(_conductor_json(item))
    except ValidationError as exc:
        return JsonResponse({"errors": _validation_errors(exc)}, status=400)
    except IntegrityError:
        return JsonResponse({"errors": {"dni": ["Ya existe un conductor con este DNI."]}}, status=409)


@login_required
@role_required(*PERSONAL_ROLES)
@require_http_methods(["GET", "POST"])
def ayudantes_api(request):
    if request.method == "GET":
        queryset = _filtered(
            request,
            Ayudante.objects.select_related("usuario").order_by("nombre", "id"),
            ("nombre", "dni", "telefono"),
        )
        page, pagination = _pagination(request, queryset)
        return JsonResponse({"results": [_ayudante_json(item) for item in page], **pagination})

    try:
        data = _payload(request)
        with transaction.atomic():
            item = _save(
                Ayudante(),
                data,
                ("nombre", "dni", "telefono", "activo", "observaciones"),
            )
        return JsonResponse(_ayudante_json(item), status=201)
    except ValidationError as exc:
        return JsonResponse({"errors": _validation_errors(exc)}, status=400)
    except IntegrityError:
        return JsonResponse({"errors": {"dni": ["Ya existe un ayudante con este DNI."]}}, status=409)


@login_required
@role_required(*PERSONAL_ROLES)
@require_http_methods(["GET", "PUT", "PATCH"])
def ayudante_api(request, pk):
    item = get_object_or_404(Ayudante.objects.select_related("usuario"), pk=pk)
    if request.method == "GET":
        return JsonResponse(_ayudante_json(item))
    try:
        data = _payload(request)
        with transaction.atomic():
            _save(
                item,
                data,
                ("nombre", "dni", "telefono", "activo", "observaciones"),
            )
        return JsonResponse(_ayudante_json(item))
    except ValidationError as exc:
        return JsonResponse({"errors": _validation_errors(exc)}, status=400)
    except IntegrityError:
        return JsonResponse({"errors": {"dni": ["Ya existe un ayudante con este DNI."]}}, status=409)
