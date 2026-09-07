"""Ayudas de filtrado/orden reutilizables para los viewsets de la API v2."""


def apply_search(queryset, term, fields):
    """Filtra `queryset` por `term` (icontains OR sobre `fields`)."""
    from django.db.models import Q

    term = (term or "").strip()
    if not term:
        return queryset
    q = Q()
    for field in fields:
        q |= Q(**{f"{field}__icontains": term})
    return queryset.filter(q)


def apply_active_filter(queryset, value, field="activo"):
    """value: 'active' | 'inactive' | cualquier otra cosa = sin filtro."""
    if value == "active":
        return queryset.filter(**{field: True})
    if value == "inactive":
        return queryset.filter(**{field: False})
    return queryset


def apply_ordering(queryset, param, allowed, default):
    """`param` como 'name' o '-createdAt'. `allowed` mapea nombre-API -> campo-ORM."""
    raw = (param or "").strip()
    if not raw:
        return queryset.order_by(*default)
    desc = raw.startswith("-")
    key = raw[1:] if desc else raw
    orm_field = allowed.get(key)
    if not orm_field:
        return queryset.order_by(*default)
    return queryset.order_by(f"-{orm_field}" if desc else orm_field)
