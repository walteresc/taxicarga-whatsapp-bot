import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.dashboard.permissions import role_required
from apps.clientes.models import Cliente
from .forms import PagoReservaForm, ReservaForm
from .models import (
    SERVICIO_CANCELADO,
    SERVICIO_FINALIZADO,
    SERVICIO_PENDIENTE,
    SERVICIO_PROGRAMADO,
    ESTADOS_SERVICIO,
    PagoReserva,
    Servicio,
)


def _safe_next(url):
    if url and url.startswith('/') and not url.startswith('//'):
        return url
    return ''


def _resumen_pagos(servicio):
    """Returns (total_pagado, saldo_pendiente) for a servicio."""
    precio = servicio.precio or Decimal("0")
    total_pagado = (
        PagoReserva.objects.filter(servicio=servicio).aggregate(
            total=Sum("monto")
        )["total"] or Decimal("0")
    )
    saldo = precio - total_pagado
    return total_pagado, saldo


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas", "Conductor", "Ayudante")
def lista_reservas(request):
    user = request.user
    servicios = Servicio.objects.select_related(
        "cliente", "asesor", "lead_origen"
    ).all()

    # Role-based filtering
    if user.groups.filter(name="Conductor").exists():
        servicios = servicios.filter(
            Q(equipodia__conductor__usuario=user)
            | Q(equipodia__ayudantes__usuario=user)
        )
    elif user.groups.filter(name="Ayudante").exists():
        servicios = servicios.filter(equipodia__ayudantes__usuario=user)

    # Filters
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "").strip()
    fecha_desde = request.GET.get("fecha_desde", "").strip()
    fecha_hasta = request.GET.get("fecha_hasta", "").strip()
    asignado = request.GET.get("asignado", "").strip()

    if q:
        servicios = servicios.filter(
            Q(cliente__nombre__icontains=q)
            | Q(cliente__telefono__icontains=q)
            | Q(codigo__icontains=q)
        )
    if estado:
        servicios = servicios.filter(estado=estado)
    if fecha_desde:
        servicios = servicios.filter(fecha_servicio__gte=fecha_desde)
    if fecha_hasta:
        servicios = servicios.filter(fecha_servicio__lte=fecha_hasta)
    if asignado == "si":
        servicios = servicios.filter(equipodia__isnull=False)
    elif asignado == "no":
        servicios = servicios.filter(equipodia__isnull=True)

    servicios = servicios.order_by('-fecha_creacion')

    # Filter by estado_pago (property – must be done in Python)
    filtro_estado_pago = request.GET.get("estado_pago", "").strip()
    if filtro_estado_pago:
        servicios = [s for s in servicios if s.estado_pago == filtro_estado_pago]
    else:
        servicios = list(servicios)

    # Metrics for header cards
    from decimal import Decimal
    total_reservas = len(servicios)
    total_cobrado = sum(
        s.total_pagado for s in servicios
        if hasattr(s, 'total_pagado')
    )
    total_saldo = sum(
        s.saldo_pendiente for s in servicios
        if hasattr(s, 'saldo_pendiente')
    )
    sin_precio = sum(
        1 for s in servicios if not s.precio
    )

    paginator = Paginator(servicios, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, "servicios/reserva_list.html", {
        "servicios": page_obj,
        "page_obj": page_obj,
        "estados": ESTADOS_SERVICIO,
        "active_section": "servicios",
        "filtro_q": q,
        "filtro_estado": estado,
        "filtro_fecha_desde": fecha_desde,
        "filtro_fecha_hasta": fecha_hasta,
        "filtro_asignado": asignado,
        "filtro_estado_pago": filtro_estado_pago,
        "total_reservas": total_reservas,
        "total_cobrado": total_cobrado,
        "total_saldo": total_saldo,
        "sin_precio": sin_precio,
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def detalle_reserva(request, pk):
    servicio = get_object_or_404(
        Servicio.objects.select_related(
            "cliente", "asesor", "lead_origen", "atendido_por", "usuario_actualizacion"
        ).prefetch_related("pagos__usuario_registro"),
        pk=pk,
    )
    pagos = servicio.pagos.all()
    total_pagado, saldo = _resumen_pagos(servicio)
    pago_form = PagoReservaForm(initial={
        "fecha_pago": timezone.now().strftime("%Y-%m-%dT%H:%M"),
    })

    # Sugerir método de pago
    metodo_sugerido = "yape"
    if servicio.tipo_comprobante in ("boleta", "factura"):
        metodo_sugerido = "bcp_sos"

    next_url = _safe_next(request.GET.get('next', ''))
    return render(request, "servicios/reserva_detail.html", {
        "s": servicio,
        "pagos": pagos,
        "total_pagado": total_pagado,
        "saldo_pendiente": saldo,
        "pago_form": pago_form,
        "metodo_sugerido": metodo_sugerido,
        "active_section": "servicios",
        "next_url": next_url,
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def crear_reserva(request):
    lead_id = request.GET.get("lead")
    initial = {}

    if lead_id:
        from apps.leads.models import Lead
        lead = get_object_or_404(Lead, pk=lead_id)
        initial["lead_origen"] = lead.pk
        initial["cliente_nombre"] = lead.cliente.nombre
        initial["cliente_telefono"] = lead.cliente.telefono
        initial["cliente_documento"] = lead.cliente.documento or ""
        initial["cliente_correo"] = lead.cliente.correo or ""
        initial["cliente_ruc"] = lead.cliente.ruc or ""
        initial["cliente_razon_social"] = lead.cliente.razon_social or ""
        initial["cliente_id"] = lead.cliente.pk
        initial["direccion_origen"] = lead.direccion_origen
        initial["direccion_destino"] = lead.direccion_destino
        initial["piso_origen"] = str(lead.piso_origen or "")
        initial["piso_destino"] = str(lead.piso_destino or "")
        initial["detalle_carga"] = lead.lista_objetos
        initial["observaciones"] = lead.nota_interna

        access_origen = []
        if lead.acceso_origen:
            access_origen.append(lead.acceso_origen)
        if lead.ascensor_origen:
            if "ascensor" not in access_origen:
                access_origen.append("ascensor")
        initial["acceso_origen_opciones"] = access_origen

        access_destino = []
        if lead.acceso_destino:
            access_destino.append(lead.acceso_destino)
        if lead.ascensor_destino:
            if "ascensor" not in access_destino:
                access_destino.append("ascensor")
        initial["acceso_destino_opciones"] = access_destino

        servicio = Servicio.objects.filter(lead_origen=lead).first()
        if servicio and servicio.estado != SERVICIO_CANCELADO:
            messages.warning(
                request,
                f"Este lead ya tiene una reserva activa ({servicio.codigo}).",
            )

    if request.method == "POST":
        form = ReservaForm(request.POST)
        if form.is_valid():
            servicio = form.save(commit=False)
            if not servicio.asesor:
                servicio.asesor = request.user
            if lead_id:
                servicio.lead_origen_id = lead_id
                servicio.estado = SERVICIO_PENDIENTE
            else:
                servicio.estado = SERVICIO_PROGRAMADO
            servicio.save()
            form._save_m2m()
            messages.success(request, f"Reserva {servicio.codigo} creada correctamente.")
            return redirect("dashboard-servicios-list")
    else:
        form = ReservaForm(initial=initial or None)

    return render(request, "servicios/reserva_form.html", {
        "form": form,
        "titulo": "Nueva Reserva",
        "submit_label": "Crear Reserva",
        "active_section": "servicios",
        "lead_id": lead_id,
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def editar_reserva(request, pk):
    servicio = get_object_or_404(Servicio, pk=pk)
    if request.method == "POST":
        next_url = _safe_next(request.POST.get('next', ''))
        form = ReservaForm(request.POST, instance=servicio)
        if form.is_valid():
            form.save()
            messages.success(request, f"Reserva {servicio.codigo} actualizada.")
            return redirect(next_url or reverse("dashboard-servicios-list"))
    else:
        next_url = _safe_next(request.GET.get('next', ''))
        form = ReservaForm(instance=servicio)

    return render(request, "servicios/reserva_form.html", {
        "form": form,
        "titulo": f"Editar Reserva {servicio.codigo}",
        "submit_label": "Guardar Cambios",
        "active_section": "servicios",
        "editando": servicio.pk,
        "next_url": next_url,
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def finalizar_reserva(request, pk):
    servicio = get_object_or_404(
        Servicio.objects.select_related("cliente").prefetch_related("pagos__usuario_registro"),
        pk=pk,
    )
    total_pagado, saldo = _resumen_pagos(servicio)

    if request.method == "POST":
        monto_final = request.POST.get("monto_final", "").strip()
        metodo_final = request.POST.get("metodo_final", "yape").strip()
        obs_final = request.POST.get("obs_final", "").strip()

        # Si hay saldo pendiente y se ingresó un monto, crear pago final
        if monto_final:
            try:
                monto_dec = Decimal(monto_final)
            except Exception:
                messages.error(request, "Monto inválido.")
                return redirect("dashboard-servicios-finalizar", pk=servicio.pk)

            if monto_dec > saldo:
                messages.error(request, "El monto no puede exceder el saldo pendiente.")
                return redirect("dashboard-servicios-finalizar", pk=servicio.pk)

            if monto_dec < saldo and not obs_final:
                messages.error(
                    request,
                    "Debe indicar el motivo en observaciones cuando el pago es menor al saldo pendiente.",
                )
                return redirect("dashboard-servicios-finalizar", pk=servicio.pk)

            PagoReserva.objects.create(
                servicio=servicio,
                concepto="final",
                metodo_pago=metodo_final,
                monto=monto_dec,
                fecha_pago=timezone.now(),
                observaciones=obs_final,
                usuario_registro=request.user,
            )

        servicio.estado = SERVICIO_FINALIZADO
        servicio.atendido_por = request.user
        servicio.usuario_actualizacion = request.user
        servicio.fecha_actualizacion_estado = timezone.now()
        servicio.save(update_fields=[
            "estado", "atendido_por", "usuario_actualizacion",
            "fecha_actualizacion_estado",
        ])
        next_url = _safe_next(request.POST.get('next', ''))
        messages.success(request, f"Reserva {servicio.codigo} marcada como finalizada.")
        return redirect(next_url or reverse("dashboard-servicios-list"))

    pagos = servicio.pagos.all()
    next_url = _safe_next(request.GET.get('next', ''))

    # Sugerir método de pago
    metodo_sugerido = "yape"
    if servicio.tipo_comprobante in ("boleta", "factura"):
        metodo_sugerido = "bcp_sos"

    return render(request, "servicios/finalizar_reserva.html", {
        "s": servicio,
        "pagos": pagos,
        "total_pagado": total_pagado,
        "saldo_pendiente": saldo,
        "metodo_sugerido": metodo_sugerido,
        "active_section": "servicios",
        "next_url": next_url,
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas", "Conductor")
def cancelar_reserva(request, pk):
    servicio = get_object_or_404(Servicio, pk=pk)
    if request.method == "POST":
        motivo = request.POST.get("motivo_cancelacion", "").strip()
        if not motivo:
            messages.error(request, "Debe ingresar un motivo de cancelación.")
            return render(request, "servicios/confirmar_cancelacion.html", {
                "servicio": servicio,
                "active_section": "servicios",
            })
        servicio.estado = SERVICIO_CANCELADO
        servicio.motivo_cancelacion = motivo
        servicio.atendido_por = request.user
        servicio.usuario_actualizacion = request.user
        servicio.fecha_actualizacion_estado = timezone.now()
        servicio.save(update_fields=[
            "estado", "motivo_cancelacion", "atendido_por",
            "usuario_actualizacion", "fecha_actualizacion_estado",
        ])
        next_url = _safe_next(request.POST.get('next', ''))
        messages.success(request, f"Reserva {servicio.codigo} cancelada.")
        return redirect(next_url or reverse("dashboard-servicios-list"))
    next_url = _safe_next(request.GET.get('next', ''))
    return render(request, "servicios/confirmar_cancelacion.html", {
        "servicio": servicio,
        "active_section": "servicios",
        "next_url": next_url,
    })


# ---------------------------------------------------------------------------
# Pagos
# ---------------------------------------------------------------------------


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def registrar_pago(request, pk):
    servicio = get_object_or_404(Servicio, pk=pk)
    if request.method == "POST":
        next_url = _safe_next(request.POST.get('next', ''))
        form = PagoReservaForm(request.POST)
        if form.is_valid():
            pago = form.save(commit=False)
            pago.servicio = servicio
            pago.usuario_registro = request.user
            pago.save()
            messages.success(
                request,
                f"Pago {pago.get_concepto_display()} de S/ {pago.monto} registrado.",
            )
            if request.POST.get("finalizar_tras_pago"):
                fin_url = reverse("dashboard-servicios-finalizar", kwargs={"pk": servicio.pk})
                if next_url:
                    fin_url += '?next=' + next_url
                return redirect(fin_url)
            det_url = reverse("dashboard-servicios-detail", kwargs={"pk": servicio.pk})
            if next_url:
                det_url += '?next=' + next_url
            return redirect(det_url)
        else:
            for field, errors in form.errors.items():
                for err in errors:
                    messages.error(request, f"{field}: {err}")
            det_url = reverse("dashboard-servicios-detail", kwargs={"pk": servicio.pk})
            if next_url:
                det_url += '?next=' + next_url
            return redirect(det_url)
    return redirect("dashboard-servicios-detail", pk=servicio.pk)


# ---------------------------------------------------------------------------
# AJAX: búsqueda de clientes
# ---------------------------------------------------------------------------

@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def buscar_clientes(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    clientes = Cliente.objects.filter(
        Q(nombre__icontains=q) | Q(telefono__icontains=q)
    )[:15]
    results = []
    for c in clientes:
        results.append({
            "id": c.pk,
            "nombre": c.nombre,
            "telefono": c.telefono,
            "documento": c.documento,
            "correo": c.correo,
            "ruc": c.ruc,
            "razon_social": c.razon_social,
        })
    return JsonResponse({"results": results})
