from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.cotizador.commercial import cambiar_estado_cotizacion
from apps.cotizador.delivery import enviar_revision_whatsapp
from apps.cotizador.models import CotizacionComercial, EnvioCotizacion, RevisionCotizacion
from apps.dashboard.permissions import whatsapp_required
from apps.whatsapp.models import WhatsAppChannel


@login_required
@whatsapp_required
def whatsapp_cotizaciones(request):
    quotes = CotizacionComercial.objects.select_related(
        "lead__cliente", "channel", "asesor", "solicitud"
    ).prefetch_related(
        Prefetch("revisiones", queryset=RevisionCotizacion.objects.order_by("-numero"), to_attr="ordered_revisions")
    )
    q = request.GET.get("q", "").strip()
    state = request.GET.get("state", "all")
    origin = request.GET.get("origin", "")
    advisor = request.GET.get("advisor", "")
    channel = request.GET.get("channel", "")
    if q:
        quotes = quotes.filter(
            Q(codigo__icontains=q)
            | Q(lead__cliente__nombre__icontains=q)
            | Q(lead__cliente__telefono__icontains=q)
            | Q(lead__distrito_origen__icontains=q)
            | Q(lead__distrito_destino__icontains=q)
        )
    valid_states = dict(CotizacionComercial.ESTADOS)
    if state in valid_states:
        quotes = quotes.filter(estado=state)
    if origin in dict(CotizacionComercial.ORIGENES):
        quotes = quotes.filter(origen=origin)
    if advisor == "bot":
        quotes = quotes.filter(asesor__isnull=True)
    elif advisor.isdigit():
        quotes = quotes.filter(asesor_id=int(advisor))
    if channel.isdigit() and WhatsAppChannel.objects.filter(pk=int(channel), activo=True).exists():
        quotes = quotes.filter(channel_id=int(channel))

    month = timezone.localdate().replace(day=1)
    base = CotizacionComercial.objects.all()
    stats = {
        "total": base.filter(creada_en__date__gte=month).count(),
        "sent": base.filter(estado__in=["enviada", "entregada"], creada_en__date__gte=month).count(),
        "negotiating": base.filter(estado="en_negociacion").count(),
        "accepted": base.filter(estado="aceptada", actualizada_en__date__gte=month).count(),
        "expired": base.filter(estado="vencida").count(),
    }
    page = Paginator(quotes.order_by("-creada_en"), 20).get_page(request.GET.get("page"))
    rows = []
    for quote in page.object_list:
        revision = quote.ordered_revisions[0] if quote.ordered_revisions else None
        rows.append({"quote": quote, "revision": revision})
    advisors = get_user_model().objects.filter(
        Q(groups__name__in=["Administrador", "Supervisor", "Asesor de Ventas"]) | Q(is_superuser=True), is_active=True
    ).distinct().order_by("first_name", "username")
    return render(request, "dashboard/whatsapp_quote_history.html", {
        "active_section": "whatsapp-cotizaciones",
        "stats": stats,
        "rows": rows,
        "page": page,
        "states": CotizacionComercial.ESTADOS,
        "origins": CotizacionComercial.ORIGENES,
        "advisors": advisors,
        "filters": {"q": q, "state": state, "origin": origin, "advisor": advisor, "channel": channel},
    })


@login_required
@whatsapp_required
def whatsapp_cotizacion_accion(request, quote_id):
    if request.method != "POST":
        return redirect("dashboard-whatsapp-cotizaciones")
    quote = get_object_or_404(CotizacionComercial, pk=quote_id)
    try:
        if request.POST.get("action") == "send":
            revision = quote.revisiones.order_by("-numero").first()
            if not revision:
                raise ValidationError("La cotización no tiene revisión.")
            envio = enviar_revision_whatsapp(revision.id, actor=request.user)
            if envio.estado == "enviado":
                messages.success(request, "Cotización enviada por WhatsApp.")
            elif envio.estado == "pendiente":
                messages.success(request, "Cotización encolada para envío por WhatsApp.")
            else:
                messages.error(request, "Envío falló; reintento programado.")
        else:
            cambiar_estado_cotizacion(quote_id, request.POST.get("state", ""))
            messages.success(request, "Estado de cotización actualizado.")
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    if request.POST.get("next") == "detail":
        return redirect("dashboard-whatsapp-cotizacion-detalle", quote_id=quote_id)
    return redirect("dashboard-whatsapp-cotizaciones")


@login_required
@whatsapp_required
def whatsapp_cotizacion_detalle(request, quote_id):
    quote = get_object_or_404(
        CotizacionComercial.objects.select_related(
            "lead__cliente", "channel", "asesor", "solicitud__conversacion"
        ).prefetch_related(
            Prefetch("revisiones", queryset=RevisionCotizacion.objects.select_related("creada_por").order_by("-numero")),
            Prefetch("revisiones__envios", queryset=EnvioCotizacion.objects.select_related("channel").order_by("-creado_en")),
        ),
        pk=quote_id,
    )
    revisions = list(quote.revisiones.all())
    latest = revisions[0] if revisions else None
    events = [{
        "date": quote.creada_en,
        "title": "Cotización creada",
        "detail": f"Origen: {quote.get_origen_display()}",
        "kind": "created",
    }]
    for revision in revisions:
        actor = revision.creada_por.get_full_name() or revision.creada_por.username if revision.creada_por else "Sistema"
        events.append({
            "date": revision.creada_en,
            "title": f"Revisión v{revision.numero} creada",
            "detail": f"S/ {revision.precio_final} · {actor}",
            "kind": "revision",
        })
        if revision.enviada_en:
            events.append({"date": revision.enviada_en, "title": f"Revisión v{revision.numero} marcada enviada", "detail": "Registro comercial", "kind": "sent"})
        for envio in revision.envios.all():
            events.append({
                "date": envio.creado_en,
                "title": f"Intento de envío: {envio.get_estado_display()}",
                "detail": envio.error_detalle or (envio.channel.nombre if envio.channel else "WhatsApp"),
                "kind": "delivery",
            })
    events.sort(key=lambda item: item["date"], reverse=True)
    return render(request, "dashboard/whatsapp_quote_detail.html", {
        "active_section": "whatsapp-cotizaciones",
        "quote": quote,
        "lead": quote.lead,
        "revisions": revisions,
        "latest": latest,
        "events": events,
    })
