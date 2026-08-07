from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.cotizador.commercial import SolicitudOcupada, asignar_solicitud, guardar_borrador
from apps.cotizador.models import SolicitudCotizacion
from apps.cotizador.services import cotizar_lead
from apps.dashboard.permissions import whatsapp_required
from apps.leads.models import Lead
from apps.whatsapp.models import WhatsAppChannel


ACTIVOS = [SolicitudCotizacion.PENDIENTE, SolicitudCotizacion.EN_PROCESO]


@login_required
@whatsapp_required
def whatsapp_por_cotizar(request):
    solicitudes = SolicitudCotizacion.objects.select_related(
        "lead__cliente", "lead__whatsapp_channel", "conversacion", "asignada_a"
    ).filter(estado__in=ACTIVOS)

    q = request.GET.get("q", "").strip()
    advisor = request.GET.get("advisor", "")
    priority = request.GET.get("priority", "")
    reason = request.GET.get("reason", "").strip()
    channel = request.GET.get("channel", "")
    if q:
        solicitudes = solicitudes.filter(
            Q(lead__cliente__nombre__icontains=q)
            | Q(lead__cliente__telefono__icontains=q)
            | Q(lead__distrito_origen__icontains=q)
            | Q(lead__distrito_destino__icontains=q)
        )
    if advisor == "unassigned":
        solicitudes = solicitudes.filter(asignada_a__isnull=True)
    elif advisor.isdigit():
        solicitudes = solicitudes.filter(asignada_a_id=int(advisor))
    if priority in dict(Lead.PRIORIDADES):
        solicitudes = solicitudes.filter(prioridad=priority)
    if reason:
        solicitudes = solicitudes.filter(motivo__icontains=reason)
    if channel.isdigit() and WhatsAppChannel.objects.filter(pk=int(channel), activo=True).exists():
        solicitudes = solicitudes.filter(lead__whatsapp_channel_id=int(channel))

    now = timezone.now()
    counts = {
        "pending": solicitudes.filter(estado=SolicitudCotizacion.PENDIENTE).count(),
        "urgent": solicitudes.filter(prioridad=Lead.PRIORIDAD_URGENTE).count(),
        "today": solicitudes.filter(creada_en__date=timezone.localdate()).count(),
    }
    paginator = Paginator(solicitudes.order_by("creada_en"), 20)
    page = paginator.get_page(request.GET.get("page"))
    rows = []
    for item in page.object_list:
        age = max(now - item.creada_en, timedelta())
        minutes = int(age.total_seconds() // 60)
        rows.append({
            "item": item,
            "route": f"{item.lead.distrito_origen or '?'} → {item.lead.distrito_destino or '?'}",
            "information": item.conversacion.porcentaje_informacion if item.conversacion_id else 0,
            "wait": _format_wait(minutes),
            "wait_minutes": minutes,
        })

    advisors = get_user_model().objects.filter(
        Q(groups__name__in=["Administrador", "Supervisor", "Asesor de Ventas"]) | Q(is_superuser=True),
        is_active=True,
    ).distinct().order_by("first_name", "username")
    reasons = SolicitudCotizacion.objects.filter(estado__in=ACTIVOS).exclude(motivo="").values_list("motivo", flat=True).distinct()[:30]
    return render(request, "dashboard/whatsapp_quote_queue.html", {
        "active_section": "whatsapp-por-cotizar",
        "counts": counts,
        "rows": rows,
        "page": page,
        "advisors": advisors,
        "priorities": Lead.PRIORIDADES,
        "reasons": reasons,
        "filters": {"q": q, "advisor": advisor, "priority": priority, "reason": reason, "channel": channel},
    })


@login_required
@whatsapp_required
def whatsapp_solicitud_accion(request, request_id):
    if request.method != "POST":
        return redirect("dashboard-whatsapp-por-cotizar")
    get_object_or_404(SolicitudCotizacion, pk=request_id)
    action = request.POST.get("action")
    try:
        if action in {"assign", "quote"}:
            solicitud = asignar_solicitud(request_id, request.user)
            messages.success(request, "Solicitud tomada correctamente.")
            if action == "quote":
                return redirect("dashboard-whatsapp-crear-cotizacion", request_id=solicitud.id)
        else:
            messages.error(request, "Accion no valida.")
    except SolicitudOcupada as exc:
        messages.error(request, exc.messages[0])
    return redirect("dashboard-whatsapp-por-cotizar")


@login_required
@whatsapp_required
def whatsapp_crear_cotizacion(request, request_id):
    solicitud = get_object_or_404(
        SolicitudCotizacion.objects.select_related(
            "lead__cliente", "lead__whatsapp_channel", "conversacion", "asignada_a"
        ).prefetch_related("cotizaciones__revisiones"),
        pk=request_id,
        estado__in=ACTIVOS,
    )
    if solicitud.asignada_a_id and solicitud.asignada_a_id != request.user.id:
        messages.error(request, "La solicitud ya fue tomada por otro asesor.")
        return redirect("dashboard-whatsapp-por-cotizar")

    lead = solicitud.lead
    technical = lead.cotizaciones.order_by("-fecha_creacion").first()
    if technical is None:
        technical = cotizar_lead(lead)
    existing = solicitud.cotizaciones.filter(estado="borrador").order_by("-creada_en").first()
    latest = existing.revisiones.order_by("-numero").first() if existing else None
    initial = {
        "price": str(latest.precio_final if latest else technical.precio_recomendado),
        "cost": str(latest.costo_estimado or "") if latest else "",
        "margin": str(latest.margen_minimo_porcentaje or 20) if latest else "20",
        "conditions": latest.condiciones if latest else "Incluye personal y unidad según el resumen del servicio.",
        "validity": latest.vigencia_dias if latest else 7,
        "internal_note": latest.observacion_interna if latest else "",
        "message": latest.mensaje_whatsapp if latest and latest.mensaje_whatsapp else _quote_message(lead, technical.precio_recomendado, 7),
    }
    if request.method == "POST":
        try:
            solicitud = asignar_solicitud(solicitud.id, request.user)
        except SolicitudOcupada as exc:
            messages.error(request, exc.messages[0])
            return redirect("dashboard-whatsapp-por-cotizar")
        initial.update({
            "price": request.POST.get("price", "").strip(),
            "cost": request.POST.get("cost", "").strip(),
            "margin": request.POST.get("margin", "20").strip(),
            "conditions": request.POST.get("conditions", "").strip(),
            "validity": request.POST.get("validity", "7").strip(),
            "internal_note": request.POST.get("internal_note", "").strip(),
            "message": request.POST.get("message", "").strip(),
        })
        try:
            price = _positive_decimal(initial["price"], "precio final")
            cost = _optional_decimal(initial["cost"], "costo estimado")
            margin = _optional_decimal(initial["margin"], "margen mínimo")
            validity = int(initial["validity"])
            if validity < 1 or validity > 90:
                raise ValidationError("La vigencia debe estar entre 1 y 90 días.")
            authorize = request.POST.get("authorize_low_margin") == "1" and request.user.is_superuser
            cotizacion, revision = guardar_borrador(
                solicitud,
                request.user,
                price,
                snapshot_servicio=_service_snapshot(lead),
                precio_sugerido_min=technical.precio_min,
                precio_sugerido_max=technical.precio_max,
                costo_estimado=cost,
                margen_minimo_porcentaje=margin,
                condiciones=initial["conditions"],
                vigencia_dias=validity,
                observacion_interna=initial["internal_note"],
                mensaje_whatsapp=initial["message"] or _quote_message(lead, price, validity),
                autoriza_bajo_margen=authorize,
            )
            messages.success(request, f"Borrador {cotizacion.codigo} v{revision.numero} guardado.")
            return redirect("dashboard-whatsapp-crear-cotizacion", request_id=solicitud.id)
        except (ValidationError, ValueError) as exc:
            detail = exc.messages[0] if isinstance(exc, ValidationError) else str(exc)
            messages.error(request, detail)

    return render(request, "dashboard/whatsapp_quote_create.html", {
        "active_section": "whatsapp-por-cotizar",
        "solicitud": solicitud,
        "lead": lead,
        "technical": technical,
        "existing": existing,
        "latest": latest,
        "form": initial,
    })


def _format_wait(minutes):
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} h"
    return f"{hours // 24} d"


def _optional_decimal(value, label):
    if value in (None, ""):
        return None
    return _positive_decimal(value, label)


def _positive_decimal(value, label):
    from decimal import Decimal, InvalidOperation
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError(f"Ingresa un {label} válido.") from exc
    if number <= 0:
        raise ValidationError(f"El {label} debe ser mayor que cero.")
    return number


def _service_snapshot(lead):
    return {
        "lead_id": lead.id,
        "cliente": lead.cliente.nombre,
        "telefono": lead.cliente.telefono,
        "tipo_servicio": lead.tipo_servicio,
        "origen": lead.distrito_origen,
        "destino": lead.distrito_destino,
        "direccion_origen": lead.direccion_origen,
        "direccion_destino": lead.direccion_destino,
        "piso_origen": lead.piso_origen,
        "piso_destino": lead.piso_destino,
        "ascensor_origen": lead.ascensor_origen,
        "ascensor_destino": lead.ascensor_destino,
        "inventario": lead.lista_objetos,
        "objetos_pesados": lead.objetos_pesados,
        "fecha": lead.fecha_servicio.isoformat() if lead.fecha_servicio else None,
        "horario": lead.horario_servicio,
        "modalidad": lead.modalidad_servicio,
    }


def _quote_message(lead, price, validity):
    return (
        f"Hola {lead.cliente.nombre or ''}, tenemos lista tu cotización para el servicio "
        f"{lead.distrito_origen or '?'} → {lead.distrito_destino or '?'}. "
        f"Precio total: S/ {price}. Válida por {validity} días. ¿Te parece bien?"
    )
