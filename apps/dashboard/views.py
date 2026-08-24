import csv

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from apps.dashboard.permissions import role_required, can_manage_pizarra,can_view_assigned_services,can_driver_update_status
from django.db.models import Count, OuterRef, Prefetch, Subquery, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from django.views.generic.base import RedirectView
from datetime import datetime
from decimal import Decimal, InvalidOperation

from apps.clientes.models import Cliente, Conversacion
from apps.cotizador.models import CotizacionComercial, RevisionCotizacion, SolicitudCotizacion
from apps.cotizador.services import cotizar_lead
from apps.leads.models import Lead
from apps.servicios.services import crear_servicio_desde_lead
from apps.whatsapp.models import BotSchedule, ConfiguracionBot, ConversacionWhatsApp, WhatsAppChannel
from apps.whatsapp.domain import devolver_al_bot, obtener_o_crear_conversacion, tomar_conversacion
from apps.whatsapp.services import send_whatsapp_message
from apps.dashboard.permissions import whatsapp_config_required, whatsapp_required


import logging
logger = logging.getLogger(__name__)


class DashboardLoginView(LoginView):
    template_name = "dashboard/login.html"
    authentication_form = AuthenticationForm
    # redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        username = request.POST.get('username', '')
        logger.info(f"[LOGIN] POST received for username={username}")

        # Log DB check
        from django.contrib.auth.models import User
        user_exists = User.objects.filter(username=username).exists()
        logger.info(f"[LOGIN] User '{username}' exists in DB: {user_exists}")

        # Log auth attempt
        from django.contrib.auth import authenticate
        auth_result = authenticate(request, username=username, password=request.POST.get('password', ''))
        logger.info(f"[LOGIN] authenticate() returned: {auth_result}")

        # Call parent
        response = super().post(request, *args, **kwargs)

        logger.info(f"[LOGIN] Response status: {response.status_code}")
        return response


login_view = DashboardLoginView.as_view()


def dashboard_logout(request):
    logout(request)
    return redirect("dashboard-login")


@login_required
#@role_required("Administrador", "Supervisor", "Asesor de Ventas", "Conductor", "Ayudante")
def dashboard_home(request, lead_id=None):
    channel_id = request.GET.get("channel")
    if channel_id and not WhatsAppChannel.objects.filter(id=channel_id, activo=True).exists():
        channel_id = None
    leads_qs = Lead.objects.select_related("cliente", "vendedor_asignado").annotate(
        _num_conversaciones=Count("cliente__conversaciones"),
    ).order_by("-fecha_creacion")
    if channel_id:
        leads_qs = leads_qs.filter(whatsapp_channel_id=channel_id)
    leads = leads_qs
    selected_lead = _selected_lead(leads, lead_id)
    if lead_id and not selected_lead:
        redirect_url = reverse("dashboard-home")
        if channel_id:
            redirect_url += f"?channel={channel_id}"
        messages.warning(request, "El lead no pertenece al canal seleccionado.")
        return redirect(redirect_url)
    grouped_leads = {
        "pendientes": leads.filter(
            estado__in=[Lead.NUEVO, Lead.EN_CONVERSACION, Lead.DATOS_INCOMPLETOS]
        )[:25],
        "cotizados": leads.filter(estado=Lead.COTIZADO)[:25],
        "asignados": leads.filter(estado=Lead.ASIGNADO)[:25],
        "cerrados": leads.filter(estado__in=[Lead.CERRADO, Lead.PERDIDO])[:25],
    }
    context = {
        "stats": _stats(),
        "grouped_leads": grouped_leads,
        "selected_lead": selected_lead,
        "conversaciones": _conversaciones(selected_lead),
        "estados": Lead.ESTADOS,
        "prioridades": Lead.PRIORIDADES,
        "dashboard_data": _dashboard_payload(grouped_leads, selected_lead, request.user, channel_id),
        "channel_id": channel_id,
        "active_section": "leads",
    }
    return render(request, "dashboard/leads.html", context)


@login_required
@require_POST
def lead_action(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    action = request.POST.get("action")

    if action == "assign_me":
        lead.vendedor_asignado = request.user
        lead.estado = Lead.ASIGNADO
        lead.save(update_fields=["vendedor_asignado", "estado"])
        messages.success(request, "Lead asignado a tu usuario.")
    elif action == "save_note":
        _append_note(lead, request.POST.get("nota", ""))
        messages.success(request, "Nota registrada.")
    elif action == "change_state":
        _change_state(lead, request.POST.get("estado"))
        messages.success(request, "Estado actualizado.")
    elif action == "change_priority":
        _change_priority(lead, request.POST.get("prioridad"))
        messages.success(request, "Prioridad actualizada.")
    elif action == "update_details":
        _update_details(lead, request.POST)
        messages.success(request, "Datos comerciales actualizados.")
    elif action == "recalculate_quote":
        _recalculate_quote(lead)
        messages.success(request, "Precio recomendado recalculado.")
    elif action == "follow_up":
        lead.fecha_ultimo_seguimiento = timezone.now()
        lead.save(update_fields=["fecha_ultimo_seguimiento"])
        messages.success(request, "Seguimiento registrado.")
    elif action == "schedule_follow_up":
        scheduled_at = _datetime_or_none(request.POST.get("fecha_proximo_seguimiento", ""))
        if scheduled_at:
            lead.fecha_proximo_seguimiento = scheduled_at
            lead.fecha_ultimo_seguimiento = timezone.now()
            lead.save(update_fields=["fecha_proximo_seguimiento", "fecha_ultimo_seguimiento"])
            messages.success(request, "Proximo seguimiento programado.")
        else:
            messages.error(request, "Ingresa una fecha y hora valida para el seguimiento.")
    elif action == "take_over":
        conversacion = obtener_o_crear_conversacion(lead)
        tomar_conversacion(conversacion.id, request.user)
        messages.success(request, "Conversacion tomada. La respuesta automatica queda pausada.")
    elif action == "release":
        conversacion = obtener_o_crear_conversacion(lead)
        devolver_al_bot(conversacion.id, request.user, "esperar")
        messages.success(request, "Conversacion liberada. La respuesta automatica vuelve a estar activa.")
    elif action == "reactivate_bot":
        lead.atencion_humana = False
        lead.bot_pausado = False
        lead.requiere_asesor = False
        lead.save(update_fields=["atencion_humana", "bot_pausado", "requiere_asesor"])
        messages.success(request, "Bot reactivado para este lead. Motivo de derivación conservado como historial.")
    elif action == "manual_reply":
        sent = _send_manual_reply(lead, request.POST.get("respuesta", ""), request.user)
        if sent:
            messages.success(request, "Respuesta registrada y enviada si WhatsApp esta configurado.")
        else:
            messages.error(request, "Escribe una respuesta antes de enviarla.")
    elif action == "send_quote":
        sent = _send_quote(
            lead,
            request.POST.get("precio_cotizado", ""),
            request.POST.get("mensaje_cotizacion", ""),
            request.user,
        )
        if sent:
            messages.success(request, "Cotizacion registrada y enviada si WhatsApp esta configurado.")
        else:
            messages.error(request, "Ingresa un precio valido para cotizar.")
    elif action == "close_won":
        closed = _close_won(lead, request.POST.get("precio_final", ""), request.user)
        if closed:
            messages.success(request, "Venta cerrada correctamente.")
        else:
            messages.error(request, "Ingresa un precio final valido para cerrar la venta.")
    elif action == "close_lost":
        closed = _close_lost(lead, request.POST.get("motivo_perdida", ""), request.user)
        if closed:
            messages.success(request, "Lead marcado como perdido.")
        else:
            messages.error(request, "Ingresa el motivo de perdida.")
    elif action == "crear_servicio":
        if lead.estado not in (Lead.COTIZADO, Lead.ASIGNADO, Lead.CERRADO):
            messages.error(request, "El lead debe estar cotizado, asignado o cerrado para crear un servicio.")
        else:
            servicio, created = crear_servicio_desde_lead(lead, usuario=request.user)
            if created:
                messages.success(request, f"Servicio {servicio.codigo} creado desde el lead.")
            else:
                messages.info(request, f"El servicio {servicio.codigo} ya existía para este lead.")
    else:
        messages.error(request, "Accion no reconocida.")

    return redirect("dashboard-lead-detail", lead_id=lead.id)


def _selected_lead(leads, lead_id):
    if lead_id:
        try:
            return leads.get(id=lead_id)
        except Lead.DoesNotExist:
            return None
    return None


def _conversaciones(lead):
    if not lead:
        return []
    return lead.cliente.conversaciones.order_by("-fecha")[:12]


def _stats():
    counts = dict(Lead.objects.values_list("estado").annotate(total=Count("id")))
    now = timezone.now()
    today = timezone.localdate()
    open_leads = Lead.objects.exclude(estado__in=[Lead.CERRADO, Lead.PERDIDO])
    closed_won = counts.get(Lead.CERRADO, 0)
    closed_lost = counts.get(Lead.PERDIDO, 0)
    closed_total = closed_won + closed_lost
    revenue = Lead.objects.filter(estado=Lead.CERRADO).aggregate(total=Sum("precio_final"))["total"] or Decimal("0.00")
    average_ticket = revenue / closed_won if closed_won else Decimal("0.00")
    conversion_rate = round((closed_won / closed_total) * 100) if closed_total else 0
    return {
        "pendientes": sum(
            counts.get(status, 0)
            for status in [Lead.NUEVO, Lead.EN_CONVERSACION, Lead.DATOS_INCOMPLETOS]
        ),
        "cotizados": counts.get(Lead.COTIZADO, 0),
        "asignados": counts.get(Lead.ASIGNADO, 0),
        "cerrados": counts.get(Lead.CERRADO, 0),
        "perdidos": counts.get(Lead.PERDIDO, 0),
        "ingresos_cerrados": f"S/ {revenue:.0f}",
        "ticket_promedio": f"S/ {average_ticket:.0f}",
        "conversion_rate": conversion_rate,
        "seguimientos_vencidos": open_leads.filter(fecha_proximo_seguimiento__lt=now).count(),
        "seguimientos_hoy": open_leads.filter(fecha_proximo_seguimiento__date=today).count(),
    }


def _dashboard_payload(grouped_leads, selected_lead, user, channel_id=None):
    conversations = [_conversation_payload(item) for item in _conversaciones(selected_lead)]
    canales = list(WhatsAppChannel.objects.filter(activo=True))
    channel = None
    if channel_id:
        channel = WhatsAppChannel.objects.filter(id=channel_id, activo=True).first()
    conf = ConfiguracionBot.obtener(channel=channel)
    schedule_filters = {}
    if channel:
        schedule_filters["channel"] = channel
    schedules_qs = BotSchedule.objects.filter(**schedule_filters).order_by("day_of_week", "start_time")
    return {
        "canales": [
            {
                "id": ch.id,
                "nombre": str(ch),
                "numero_visible": ch.numero_visible,
                "asesor_nombre": str(ch.asesor) if ch.asesor else "Sin asesor",
                "activo": ch.activo,
                "lead_count": ch.leads.count(),
            }
            for ch in canales
        ],
        "channel_id": channel.id if channel else None,
        "user": {"username": user.username},
        "stats": _stats(),
        "botConfig": _bot_config_payload(conf, schedules_qs),
        "botSettingsUrl": "/api/bot-settings/",
        "botSchedulesUrl": "/api/bot-schedules/",
        "groups": [
            {
                "key": "pendientes",
                "label": "Pendientes",
                "color": "amber-darken-3",
                "icon": "mdi-clock-outline",
                "leads": [_lead_payload(lead, channel_id) for lead in grouped_leads["pendientes"]],
            },
            {
                "key": "cotizados",
                "label": "Cotizados",
                "color": "blue-darken-2",
                "icon": "mdi-file-document-check-outline",
                "leads": [_lead_payload(lead, channel_id) for lead in grouped_leads["cotizados"]],
            },
            {
                "key": "asignados",
                "label": "Asignados",
                "color": "teal-darken-2",
                "icon": "mdi-account-check-outline",
                "leads": [_lead_payload(lead, channel_id) for lead in grouped_leads["asignados"]],
            },
            {
                "key": "cerrados",
                "label": "Cerrados",
                "color": "slate",
                "icon": "mdi-archive-check-outline",
                "leads": [_lead_payload(lead, channel_id) for lead in grouped_leads["cerrados"]],
            },
        ],
        "selectedLead": _lead_payload(selected_lead, channel_id) if selected_lead else None,
        "conversations": conversations,
        "messages": _message_payloads(conversations),
        "states": [{"value": value, "label": label} for value, label in Lead.ESTADOS],
        "priorities": [{"value": value, "label": label} for value, label in Lead.PRIORIDADES],
        "quickReplies": _quick_replies(),
        "createLeadUrl": "/dashboard/leads/nuevo/",
        "exportLeadsUrl": "/dashboard/exportar/leads.csv",
        "today": timezone.localdate().isoformat(),
    }


def _format_time_value(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    if isinstance(value, str):
        return value
    return str(value)


def _bot_config_payload(conf, schedules_qs=None):
    return {
        "bot_activo": conf.bot_activo,
        "modo_atencion": conf.modo_atencion,
        "hora_inicio_bot": _format_time_value(conf.hora_inicio_bot),
        "hora_fin_bot": _format_time_value(conf.hora_fin_bot),
        "lunes_activo": conf.lunes_activo,
        "martes_activo": conf.martes_activo,
        "miercoles_activo": conf.miercoles_activo,
        "jueves_activo": conf.jueves_activo,
        "viernes_activo": conf.viernes_activo,
        "sabado_activo": conf.sabado_activo,
        "domingo_activo": conf.domingo_activo,
        "mensaje_fuera_horario": conf.mensaje_fuera_horario,
        "override_activo": conf.override_activo,
        "override_modo": conf.override_modo,
        "override_desde": conf.override_desde.isoformat() if conf.override_desde else None,
        "override_hasta": conf.override_hasta.isoformat() if conf.override_hasta else None,
        "override_motivo": conf.override_motivo,
        "schedules": [
            {
                "id": s.id,
                "day_of_week": s.day_of_week,
                "start_time": _format_time_value(s.start_time),
                "end_time": _format_time_value(s.end_time),
                "is_active": s.is_active,
            }
            for s in (schedules_qs or [])
        ],
    }


def _quick_replies():
    return [
        {
            "key": "confirmar_datos",
            "label": "Confirmar datos",
            "target": "respuesta",
            "icon": "mdi-clipboard-check-outline",
            "text": (
                "Hola {cliente}, confirmo los datos del servicio: origen {origen}, "
                "destino {destino}. Con eso reviso la mejor opcion y le respondo en breve."
            ),
        },
        {
            "key": "pedir_fotos",
            "label": "Pedir fotos",
            "target": "respuesta",
            "icon": "mdi-camera-outline",
            "text": (
                "Para afinar la cotizacion, por favor envieme fotos de los objetos "
                "principales y del acceso en origen y destino."
            ),
        },
        {
            "key": "seguimiento",
            "label": "Seguimiento",
            "target": "respuesta",
            "icon": "mdi-phone-forward-outline",
            "text": (
                "Hola {cliente}, le escribo para saber si seguimos adelante con la "
                "coordinacion del servicio de {origen} a {destino}."
            ),
        },
        {
            "key": "cierre_servicio",
            "label": "Cerrar servicio",
            "target": "respuesta",
            "icon": "mdi-calendar-check-outline",
            "text": (
                "Listo, quedamos atentos a su confirmacion de fecha y horario para dejar "
                "el servicio programado."
            ),
        },
        {
            "key": "cotizacion",
            "label": "Cotizacion",
            "target": "cotizacion",
            "icon": "mdi-currency-usd",
            "text": (
                "Hola {cliente}, para el servicio de {origen} a {destino}, la cotizacion "
                "queda en S/ {precio}. Incluye movilidad y personal segun lo conversado."
            ),
        },
    ]


@login_required
def export_leads_csv(request):
    scope = request.GET.get("estado", "todos")
    leads = _leads_for_export(scope)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"taxicarga_leads_{scope}_{timezone.localdate().isoformat()}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        [
            "id",
            "cliente",
            "telefono",
            "tipo_servicio",
            "origen",
            "destino",
            "fecha_servicio",
            "horario_servicio",
            "estado",
            "prioridad",
            "vendedor",
            "precio_recomendado",
            "precio_cotizado",
            "precio_final",
            "fecha_cierre",
            "motivo_perdida",
            "proximo_seguimiento",
            "ultimo_seguimiento",
            "atencion_humana",
            "objetos",
            "nota_interna",
        ]
    )
    for lead in leads:
        writer.writerow(
            [
                lead.id,
                lead.cliente.nombre,
                lead.cliente.telefono,
                lead.tipo_servicio,
                lead.distrito_origen,
                lead.distrito_destino,
                lead.fecha_servicio or "",
                lead.horario_servicio,
                lead.estado,
                lead.prioridad,
                lead.vendedor_asignado or "",
                lead.precio_recomendado or "",
                lead.precio_cotizado or "",
                lead.precio_final or "",
                _datetime_label(lead.fecha_cierre),
                lead.motivo_perdida,
                _datetime_label(lead.fecha_proximo_seguimiento),
                _datetime_label(lead.fecha_ultimo_seguimiento),
                "si" if lead.atencion_humana else "no",
                lead.lista_objetos,
                lead.nota_interna,
            ]
        )
    return response


@login_required
@require_POST
def create_lead(request):
    phone = request.POST.get("telefono", "").strip()
    if not phone:
        messages.error(request, "El telefono es requerido para crear el lead.")
        return redirect("dashboard-home")

    cliente, _ = Cliente.objects.get_or_create(telefono=phone)
    cliente.nombre = request.POST.get("nombre", "").strip() or cliente.nombre
    cliente.ultima_interaccion = timezone.now()
    cliente.save(update_fields=["nombre", "ultima_interaccion"])

    lead = Lead.objects.create(
        cliente=cliente,
        tipo_servicio=request.POST.get("tipo_servicio", "").strip(),
        distrito_origen=request.POST.get("distrito_origen", "").strip(),
        distrito_destino=request.POST.get("distrito_destino", "").strip(),
        lista_objetos=request.POST.get("lista_objetos", "").strip(),
        fecha_servicio=_date_or_none(request.POST.get("fecha_servicio", "")),
        horario_servicio=request.POST.get("horario_servicio", "").strip(),
        prioridad=request.POST.get("prioridad") or Lead.PRIORIDAD_MEDIA,
        vendedor_asignado=request.user,
        estado=Lead.ASIGNADO,
        atencion_humana=True,
        nota_interna=request.POST.get("nota_interna", "").strip(),
    )
    messages.success(request, "Lead creado y asignado a tu usuario.")
    return redirect("dashboard-lead-detail", lead_id=lead.id)


def _lead_payload(lead, channel_id=None):
    from apps.leads.route import access_summary, route_summary
    completion = _completion_payload(lead)
    detail_url = f"/dashboard/leads/{lead.id}/"
    if channel_id:
        detail_url += f"?channel={channel_id}"
    return {
        "id": lead.id,
        "cliente": lead.cliente.nombre or lead.cliente.telefono,
        "telefono": lead.cliente.telefono,
        "tipoServicio": lead.tipo_servicio or "servicio",
        "distritoOrigen": lead.distrito_origen or "-",
        "distritoDestino": lead.distrito_destino or "-",
        "ruta": (route_summary(lead) or "-").replace(" → ", " -> "),
        "accesosRuta": access_summary(lead) or "-",
        "ubicaciones": [
            {
                "orden": order,
                "tipo": location.tipo,
                "distrito": location.distrito,
                "direccion": location.direccion,
                "piso": location.piso,
                "ascensor": _bool_label(location.ascensor),
                "accesoCamion": _bool_label(location.acceso_camion),
            }
            for order, location in enumerate(lead.ubicaciones.order_by("orden", "id"))
        ],
        "fechaServicio": lead.fecha_servicio.isoformat() if lead.fecha_servicio else "",
        "horarioServicio": lead.horario_servicio or "",
        "estado": lead.estado,
        "prioridad": lead.prioridad,
        "atencionHumana": lead.atencion_humana,
        "vendedor": str(lead.vendedor_asignado) if lead.vendedor_asignado else "Sin asignar",
        "pisoOrigen": lead.piso_origen if lead.piso_origen is not None else "-",
        "pisoDestino": lead.piso_destino if lead.piso_destino is not None else "-",
        "pisoOrigenInput": lead.piso_origen if lead.piso_origen is not None else "",
        "pisoDestinoInput": lead.piso_destino if lead.piso_destino is not None else "",
        "ascensorOrigen": _bool_label(lead.ascensor_origen),
        "ascensorDestino": _bool_label(lead.ascensor_destino),
        "ascensorOrigenInput": _bool_input_value(lead.ascensor_origen),
        "ascensorDestinoInput": _bool_input_value(lead.ascensor_destino),
        "listaObjetos": lead.lista_objetos or "-",
        "listaObjetosInput": lead.lista_objetos or "",
        "cantidadOperarios": lead.cantidad_operarios,
        "incluyePersonal": _bool_label(lead.incluye_personal_carga),
        "embalaje": lead.modalidad_servicio or "sin embalaje",
        "requiereDesarmado": _bool_label(lead.requiere_desarmado),
        "requiereArmado": _bool_label(lead.requiere_armado),
        "reserva": lead.servicio_generado.codigo if hasattr(lead, "servicio_generado") else "Pendiente",
        "notaInterna": lead.nota_interna or "",
        "precioRecomendado": str(lead.precio_recomendado or ""),
        "precioCotizado": str(lead.precio_cotizado or ""),
        "precioFinal": str(lead.precio_final or ""),
        "precioEstimadoMin": str(lead.precio_estimado_min or ""),
        "precioEstimadoMax": str(lead.precio_estimado_max or ""),
        "motivoPerdida": lead.motivo_perdida or "",
        "fechaCierre": _datetime_label(lead.fecha_cierre),
        "ultimaCotizacion": _latest_quote_payload(lead),
        "requiereAsesor": lead.requiere_asesor,
        "motivoDerivacion": lead.motivo_derivacion or "",
        "botPausado": lead.bot_pausado,
        "guardPausado": lead.bot_pausado and "WhatsApp Business" in (lead.motivo_derivacion or ""),
        "conversacionAvanzada": _conversacion_avanzada(lead),
        "whatsappChannel": lead.whatsapp_channel_id,
        "fechaDerivacion": _datetime_label(lead.fecha_derivacion),
        "fechaUltimoSeguimiento": _datetime_label(lead.fecha_ultimo_seguimiento),
        "fechaProximoSeguimiento": _datetime_label(lead.fecha_proximo_seguimiento),
        "fechaProximoSeguimientoInput": _datetime_input_value(lead.fecha_proximo_seguimiento),
        "seguimientoVencido": _is_overdue(lead),
        "seguimientoHoy": _is_due_today(lead),
        "completion": completion,
        "detailUrl": detail_url,
        "actionUrl": f"/dashboard/leads/{lead.id}/accion/",
    }


def _completion_payload(lead):
    checks = [
        ("tipo_servicio", "Servicio", bool(lead.tipo_servicio)),
        ("ruta", "Origen y destino", bool(lead.distrito_origen and lead.distrito_destino)),
        ("objetos", "Lista de objetos", bool(lead.lista_objetos)),
        ("fecha", "Fecha del servicio", bool(lead.fecha_servicio)),
        ("horario", "Horario", bool(lead.horario_servicio)),
        (
            "accesos",
            "Pisos y ascensores",
            all(
                value is not None
                for value in [
                    lead.piso_origen,
                    lead.piso_destino,
                    lead.ascensor_origen,
                    lead.ascensor_destino,
                ]
            ),
        ),
        ("precio", "Precio recomendado o cotizado", bool(lead.precio_recomendado or lead.precio_cotizado)),
    ]
    completed = sum(1 for _, _, is_done in checks if is_done)
    total = len(checks)
    missing = [{"key": key, "label": label} for key, label, is_done in checks if not is_done]
    items = [{"key": key, "label": label, "done": is_done} for key, label, is_done in checks]
    percent = round((completed / total) * 100) if total else 0
    return {
        "completed": completed,
        "total": total,
        "percent": percent,
        "label": f"{completed}/{total} datos",
        "ready": percent >= 80,
        "items": items,
        "missing": missing,
    }


def _leads_for_export(scope):
    leads = Lead.objects.select_related("cliente", "vendedor_asignado").order_by("-fecha_creacion")
    if scope == "pendientes":
        return leads.filter(estado__in=[Lead.NUEVO, Lead.EN_CONVERSACION, Lead.DATOS_INCOMPLETOS])
    if scope == "cotizados":
        return leads.filter(estado=Lead.COTIZADO)
    if scope == "asignados":
        return leads.filter(estado=Lead.ASIGNADO)
    if scope == "cerrados":
        return leads.filter(estado__in=[Lead.CERRADO, Lead.PERDIDO])
    return leads


def _latest_quote_payload(lead):
    quote = lead.cotizaciones.first()
    if not quote:
        return None
    return {
        "precioMin": str(quote.precio_min),
        "precioMax": str(quote.precio_max),
        "precioRecomendado": str(quote.precio_recomendado),
        "similares": quote.servicios_similares_encontrados,
        "explicacion": quote.explicacion,
        "fecha": _datetime_label(quote.fecha_creacion),
    }


def _conversacion_avanzada(lead):
    from apps.whatsapp.utils import ESTADOS_AVANZADOS
    if lead.estado in ESTADOS_AVANZADOS:
        return True
    if hasattr(lead, "etapa_conversacion") and lead.etapa_conversacion in ESTADOS_AVANZADOS:
        return True
    if lead.atencion_humana or lead.requiere_asesor or lead.bot_pausado:
        return True
    if lead.motivo_derivacion:
        return True
    if lead.fecha_creacion and (timezone.now() - lead.fecha_creacion).days > 3:
        return True
    return False


def _conversation_payload(conversation):
    return {
        "fecha": timezone.localtime(conversation.fecha).strftime("%Y-%m-%d %H:%M"),
        "entrada": conversation.mensaje_entrada or "",
        "salida": conversation.mensaje_salida or "",
    }


def _message_payloads(conversations):
    messages = []
    for index, conversation in enumerate(reversed(conversations)):
        if conversation["entrada"]:
            messages.append(
                {
                    "key": f"{index}-entrada",
                    "fecha": conversation["fecha"],
                    "author": "Cliente",
                    "direction": "in",
                    "text": conversation["entrada"],
                    "icon": "mdi-account-outline",
                }
            )
        if conversation["salida"]:
            messages.append(
                {
                    "key": f"{index}-salida",
                    "fecha": conversation["fecha"],
                    "author": "TaxiCarga",
                    "direction": "out",
                    "text": conversation["salida"],
                    "icon": "mdi-truck-fast-outline",
                }
            )
    return messages


def _bool_label(value):
    if value is True:
        return "Si"
    if value is False:
        return "No"
    return "-"


def _bool_input_value(value):
    if value is True:
        return "si"
    if value is False:
        return "no"
    return "sin_dato"


def _datetime_label(value):
    if not value:
        return "-"
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")


def _datetime_input_value(value):
    if not value:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


def _is_overdue(lead):
    return bool(
        lead.fecha_proximo_seguimiento
        and lead.fecha_proximo_seguimiento < timezone.now()
        and lead.estado not in {Lead.CERRADO, Lead.PERDIDO}
    )


def _is_due_today(lead):
    return bool(
        lead.fecha_proximo_seguimiento
        and timezone.localtime(lead.fecha_proximo_seguimiento).date() == timezone.localdate()
        and lead.estado not in {Lead.CERRADO, Lead.PERDIDO}
    )


def _append_note(lead, note):
    note = note.strip()
    if not note:
        return
    timestamp = timezone.localtime().strftime("%Y-%m-%d %H:%M")
    lead.nota_interna = f"{lead.nota_interna}\n[{timestamp}] {note}".strip()
    lead.fecha_ultimo_seguimiento = timezone.now()
    lead.save(update_fields=["nota_interna", "fecha_ultimo_seguimiento"])


def _change_state(lead, estado):
    valid_states = {value for value, _ in Lead.ESTADOS}
    if estado not in valid_states:
        return
    lead.estado = estado
    update_fields = ["estado"]
    if estado in {Lead.CERRADO, Lead.PERDIDO}:
        lead.fecha_cierre = timezone.now()
        update_fields.append("fecha_cierre")
    lead.save(update_fields=update_fields)


def _change_priority(lead, prioridad):
    valid_priorities = {value for value, _ in Lead.PRIORIDADES}
    if prioridad not in valid_priorities:
        return
    lead.prioridad = prioridad
    lead.save(update_fields=["prioridad"])


def _update_details(lead, data):
    lead.tipo_servicio = data.get("tipo_servicio", "").strip()
    lead.distrito_origen = data.get("distrito_origen", "").strip()
    lead.distrito_destino = data.get("distrito_destino", "").strip()
    lead.lista_objetos = data.get("lista_objetos", "").strip()
    lead.fecha_servicio = _date_or_none(data.get("fecha_servicio", ""))
    lead.horario_servicio = data.get("horario_servicio", "").strip()
    lead.piso_origen = _int_or_none(data.get("piso_origen", ""))
    lead.piso_destino = _int_or_none(data.get("piso_destino", ""))
    lead.ascensor_origen = _bool_or_none(data.get("ascensor_origen", ""))
    lead.ascensor_destino = _bool_or_none(data.get("ascensor_destino", ""))
    lead.fecha_ultimo_seguimiento = timezone.now()
    lead.save(
        update_fields=[
            "tipo_servicio",
            "distrito_origen",
            "distrito_destino",
            "lista_objetos",
            "fecha_servicio",
            "horario_servicio",
            "piso_origen",
            "piso_destino",
            "ascensor_origen",
            "ascensor_destino",
            "fecha_ultimo_seguimiento",
        ]
    )


def _recalculate_quote(lead):
    quote = cotizar_lead(lead)
    lead.precio_estimado_min = quote.precio_min
    lead.precio_estimado_max = quote.precio_max
    lead.precio_recomendado = quote.precio_recomendado
    lead.fecha_ultimo_seguimiento = timezone.now()
    lead.save(
        update_fields=[
            "precio_estimado_min",
            "precio_estimado_max",
            "precio_recomendado",
            "fecha_ultimo_seguimiento",
        ]
    )
    return quote


def _send_manual_reply(lead, reply, user):
    reply = reply.strip()
    if not reply:
        return False
    conversacion_whatsapp = obtener_o_crear_conversacion(lead)
    tomar_conversacion(conversacion_whatsapp.id, user)
    send_whatsapp_message(
        lead.cliente.telefono, reply, channel=conversacion_whatsapp.channel,
    )
    Conversacion.objects.create(
        cliente=lead.cliente,
        mensaje_entrada="",
        mensaje_salida=reply,
        canal=Conversacion.CANAL_WHATSAPP,
    )
    lead.fecha_ultimo_seguimiento = timezone.now()
    lead.atencion_humana = True
    update_fields = ["fecha_ultimo_seguimiento", "atencion_humana"]
    if not lead.vendedor_asignado:
        lead.vendedor_asignado = user
        update_fields.append("vendedor_asignado")
    lead.save(update_fields=update_fields)
    return True


def _send_quote(lead, price, custom_message, user):
    quoted_price = _decimal_or_none(price)
    if quoted_price is None or quoted_price <= 0:
        return False
    conversacion_whatsapp = obtener_o_crear_conversacion(lead)
    tomar_conversacion(conversacion_whatsapp.id, user)
    message = custom_message.strip() or _default_quote_message(lead, quoted_price)
    send_whatsapp_message(
        lead.cliente.telefono, message, channel=conversacion_whatsapp.channel,
    )
    Conversacion.objects.create(
        cliente=lead.cliente,
        mensaje_entrada="",
        mensaje_salida=message,
        canal=Conversacion.CANAL_WHATSAPP,
    )
    lead.precio_cotizado = quoted_price
    lead.estado = Lead.COTIZADO
    lead.atencion_humana = True
    lead.fecha_ultimo_seguimiento = timezone.now()
    update_fields = [
        "precio_cotizado",
        "estado",
        "atencion_humana",
        "fecha_ultimo_seguimiento",
    ]
    if not lead.vendedor_asignado:
        lead.vendedor_asignado = user
        update_fields.append("vendedor_asignado")
    lead.save(update_fields=update_fields)
    return True


def _close_won(lead, final_price, user):
    price = _decimal_or_none(final_price)
    if price is None or price <= 0:
        return False
    lead.precio_final = price
    lead.estado = Lead.CERRADO
    lead.fecha_cierre = timezone.now()
    lead.fecha_ultimo_seguimiento = timezone.now()
    lead.atencion_humana = True
    update_fields = [
        "precio_final",
        "estado",
        "fecha_cierre",
        "fecha_ultimo_seguimiento",
        "atencion_humana",
    ]
    if not lead.vendedor_asignado:
        lead.vendedor_asignado = user
        update_fields.append("vendedor_asignado")
    lead.save(update_fields=update_fields)
    return True


def _close_lost(lead, reason, user):
    reason = reason.strip()
    if not reason:
        return False
    lead.motivo_perdida = reason
    lead.estado = Lead.PERDIDO
    lead.fecha_cierre = timezone.now()
    lead.fecha_ultimo_seguimiento = timezone.now()
    lead.atencion_humana = True
    update_fields = [
        "motivo_perdida",
        "estado",
        "fecha_cierre",
        "fecha_ultimo_seguimiento",
        "atencion_humana",
    ]
    if not lead.vendedor_asignado:
        lead.vendedor_asignado = user
        update_fields.append("vendedor_asignado")
    lead.save(update_fields=update_fields)
    return True


@login_required
def placeholder_campo(request):
    return render(request, "campo/placeholder.html", {
        "active_section": "campo",
        "title": "Gestión de Campo",
        "icon": "mdi-map-marker-outline",
        "description": "Próximamente: asignación de rutas, seguimiento de unidades y coordinación con personal de campo.",
    })


@login_required
def placeholder_personal(request):
    return render(request, "campo/placeholder.html", {
        "active_section": "personal",
        "title": "Gestión de Personal",
        "icon": "mdi-account-group-outline",
        "description": "Próximamente: administración de conductores, ayudantes, horarios y asignación de personal.",
    })


@login_required
def placeholder_reportes(request):
    return render(request, "campo/placeholder.html", {
        "active_section": "reportes",
        "title": "Reportes",
        "icon": "mdi-chart-bar",
        "description": "Próximamente: reportes de ventas, desempeño, ingresos y análisis de datos.",
    })


@login_required
def placeholder_admin(request):
    return render(request, "campo/placeholder.html", {
        "active_section": "admin",
        "title": "Administración",
        "icon": "mdi-shield-account-outline",
        "description": "Próximamente: configuración del sistema, usuarios, roles y parámetros generales.",
    })


@login_required
def placeholder_whatsapp(request):
    return render(request, "dashboard/whatsapp.html", {
        "active_section": "whatsapp",
    })


@login_required
@whatsapp_required
def whatsapp_conversaciones_base(request):
    conversaciones = ConversacionWhatsApp.objects.select_related(
        "cliente", "lead", "channel", "responsable"
    )
    channel_id = _active_channel_id(request)
    if channel_id:
        conversaciones = conversaciones.filter(channel_id=channel_id)
    rows = [
        {
            "primary": conversacion.cliente.nombre or conversacion.cliente.telefono,
            "secondary": conversacion.cliente.telefono,
            "route": str(conversacion.channel) if conversacion.channel_id else "Sin canal",
            "status": conversacion.get_estado_atencion_display(),
            "detail": conversacion.responsable.get_full_name() or conversacion.responsable.username
            if conversacion.responsable_id
            else "Bot",
        }
        for conversacion in conversaciones[:20]
    ]
    return _render_whatsapp_base(
        request,
        title="Conversaciones",
        subtitle="Bandeja compartida conectada a sesiones reales",
        active_section="whatsapp-conversaciones",
        stats=[
            ("Total", conversaciones.count()),
            ("Bot atendiendo", conversaciones.filter(estado_atencion=ConversacionWhatsApp.ATENCION_BOT).count()),
            ("Asesor atendiendo", conversaciones.filter(estado_atencion=ConversacionWhatsApp.ATENCION_ASESOR).count()),
            ("Por cotizar", conversaciones.filter(estado_cotizacion=ConversacionWhatsApp.COTIZACION_PENDIENTE).count()),
        ],
        rows=rows,
        columns=("Cliente", "Telefono", "Canal", "Estado", "Responsable"),
        empty_message="No existen conversaciones para el canal seleccionado.",
    )


@login_required
@whatsapp_required
def whatsapp_por_cotizar_base(request):
    solicitudes = SolicitudCotizacion.objects.select_related(
        "lead__cliente", "lead__whatsapp_channel", "asignada_a"
    ).filter(estado__in=[SolicitudCotizacion.PENDIENTE, SolicitudCotizacion.EN_PROCESO])
    channel_id = _active_channel_id(request)
    if channel_id:
        solicitudes = solicitudes.filter(lead__whatsapp_channel_id=channel_id)
    rows = [
        {
            "primary": solicitud.lead.cliente.nombre or solicitud.lead.cliente.telefono,
            "secondary": f"{solicitud.lead.distrito_origen or '?'} → {solicitud.lead.distrito_destino or '?'}",
            "route": solicitud.motivo or "Revision manual",
            "status": solicitud.get_estado_display(),
            "detail": solicitud.asignada_a.username if solicitud.asignada_a_id else "Sin asignar",
        }
        for solicitud in solicitudes[:20]
    ]
    return _render_whatsapp_base(
        request,
        title="Por cotizar",
        subtitle="Cola real de solicitudes pendientes",
        active_section="whatsapp-por-cotizar",
        stats=[
            ("Pendientes", solicitudes.filter(estado=SolicitudCotizacion.PENDIENTE).count()),
            ("En proceso", solicitudes.filter(estado=SolicitudCotizacion.EN_PROCESO).count()),
            ("Urgentes", solicitudes.filter(prioridad=Lead.PRIORIDAD_URGENTE).count()),
        ],
        rows=rows,
        columns=("Cliente", "Ruta", "Motivo", "Estado", "Asesor"),
        empty_message="No existen solicitudes activas por cotizar.",
    )


@login_required
@whatsapp_required
def whatsapp_cotizaciones_base(request):
    cotizaciones = CotizacionComercial.objects.select_related(
        "lead__cliente", "channel", "asesor"
    ).prefetch_related(
        Prefetch("revisiones", queryset=RevisionCotizacion.objects.order_by("-numero"), to_attr="revisiones_ordenadas")
    )
    channel_id = _active_channel_id(request)
    if channel_id:
        cotizaciones = cotizaciones.filter(channel_id=channel_id)
    rows = []
    for cotizacion in cotizaciones[:20]:
        revision = cotizacion.revisiones_ordenadas[0] if cotizacion.revisiones_ordenadas else None
        rows.append({
            "primary": cotizacion.codigo,
            "secondary": cotizacion.lead.cliente.nombre or cotizacion.lead.cliente.telefono,
            "route": f"S/ {revision.precio_final}" if revision else "Sin revision",
            "status": cotizacion.get_estado_display(),
            "detail": cotizacion.asesor.username if cotizacion.asesor_id else "Bot",
        })
    return _render_whatsapp_base(
        request,
        title="Cotizaciones",
        subtitle="Historial comercial conectado a cotizaciones versionadas",
        active_section="whatsapp-cotizaciones",
        stats=[
            ("Total", cotizaciones.count()),
            ("Borradores", cotizaciones.filter(estado="borrador").count()),
            ("Enviadas", cotizaciones.filter(estado__in=["enviada", "entregada"]).count()),
            ("Aceptadas", cotizaciones.filter(estado="aceptada").count()),
        ],
        rows=rows,
        columns=("Codigo", "Cliente", "Precio", "Estado", "Generada por"),
        empty_message="Todavia no existen cotizaciones comerciales.",
    )


@login_required
@whatsapp_config_required
def whatsapp_configuracion(request):
    return render(request, "dashboard/whatsapp.html", {"active_section": "whatsapp-configuracion"})


def _render_whatsapp_base(request, **context):
    context["stats"] = [{"label": label, "value": value} for label, value in context["stats"]]
    return render(request, "dashboard/whatsapp_module_base.html", context)


def _active_channel_id(request):
    channel_id = request.GET.get("channel", "")
    if not channel_id.isdigit():
        return None
    return WhatsAppChannel.objects.filter(pk=int(channel_id), activo=True).values_list("id", flat=True).first()


@login_required
def placeholder_canales(request):
    return render(request, "campo/placeholder.html", {
        "active_section": "canales",
        "title": "Canales WhatsApp",
        "icon": "mdi-whatsapp",
        "description": "Próximamente: administración de canales WhatsApp, números, asignación de asesores y estado.",
    })


def _default_quote_message(lead, price):
    route = ""
    if lead.distrito_origen or lead.distrito_destino:
        route = f" de {lead.distrito_origen or 'origen'} a {lead.distrito_destino or 'destino'}"
    return (
        f"Listo, para el servicio{route}, la cotizacion queda en S/ {price:.0f}. "
        "Incluye movilidad y personal segun lo conversado. Si le parece bien, coordinamos la hora."
    )


@login_required
def stats_api(request):
    """API endpoint para auto-refresh de estadísticas."""
    channel_id = request.GET.get("channel")
    stats = _stats()

    # Filtrar por canal si se especifica
    if channel_id:
        try:
            channel = WhatsAppChannel.objects.get(id=channel_id, activo=True)
            channel_stats = dict(
                Lead.objects.filter(whatsapp_channel=channel)
                .values_list("estado")
                .annotate(total=Count("id"))
            )
            stats = {
                "pendientes": sum(
                    channel_stats.get(status, 0)
                    for status in [Lead.NUEVO, Lead.EN_CONVERSACION, Lead.DATOS_INCOMPLETOS]
                ),
                "cotizados": channel_stats.get(Lead.COTIZADO, 0),
                "asignados": channel_stats.get(Lead.ASIGNADO, 0),
                "cerrados": channel_stats.get(Lead.CERRADO, 0),
                "perdidos": channel_stats.get(Lead.PERDIDO, 0),
            }
        except WhatsAppChannel.DoesNotExist:
            pass

    return JsonResponse({"stats": stats})


def _decimal_or_none(value):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _date_or_none(value):
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _int_or_none(value):
    value = str(value).strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _bool_or_none(value):
    if value == "si":
        return True
    if value == "no":
        return False
    return None


def _datetime_or_none(value):
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


@login_required
@require_http_methods(["GET"])
def api_conversaciones_activas(request):
    """API endpoint: /dashboard/whatsapp/conversaciones/api/active/
    Returns active conversations ordered by ultima_actividad DESC."""
    convs = ConversacionWhatsApp.objects.filter(
        cerrada_en__isnull=True
    ).select_related(
        'cliente'
    ).order_by('-ultima_actividad')[:100]

    conversations = []
    for conv in convs:
        conversations.append({
            'id': conv.id,
            'cliente_id': conv.cliente_id,
            'cliente_nombre': conv.cliente.nombre if conv.cliente else '',
            'preview': conv.resumen or '',
            'ultima_actividad': conv.ultima_actividad.isoformat() if conv.ultima_actividad else None,
            'estado': conv.estado_atencion,
        })

    return JsonResponse({
        'conversations': conversations,
        'count': len(conversations),
    })
