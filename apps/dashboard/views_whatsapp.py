from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
import json
import logging
import re

logger = logging.getLogger(__name__)

def _get_message_preview(mensaje):
  """Generar preview del mensaje según su tipo"""
  if not mensaje:
    return "Conversación nueva"

  tipo_map = {
    "texto": lambda m: (m.contenido or "")[:100],
    "imagen": lambda m: "📷 Foto",
    "audio": lambda m: "🎤 Audio",
    "documento": lambda m: f"📄 Documento",
    "ubicacion": lambda m: "📍 Ubicación",
    "sticker": lambda m: "Sticker",
    "sistema": lambda m: "Mensaje del sistema",
  }

  generator = tipo_map.get(mensaje.tipo, lambda m: "Mensaje no disponible")
  return generator(mensaje)

from apps.clientes.models import Conversacion as ConversacionLegacy
from apps.dashboard.permissions import whatsapp_required
from apps.whatsapp.domain import (
    ConversacionOcupada,
    TransicionConversacionInvalida,
    cerrar_conversacion,
    devolver_al_bot,
    enviar_a_cotizar,
    tomar_conversacion,
)
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp, WhatsAppChannel
from apps.whatsapp.services import send_whatsapp_message, send_crm_message, send_crm_media_message


@login_required
@whatsapp_required
def whatsapp_conversaciones(request):
    conversaciones = ConversacionWhatsApp.objects.select_related(
        "cliente", "lead", "channel", "responsable"
    )
    conversaciones = _filtrar_conversaciones(conversaciones, request)
    seleccionada = _seleccionar_conversacion(conversaciones, request.GET.get("conversation"))
    mensajes_chat = _mensajes_para_chat(seleccionada)
    lead = seleccionada.lead if seleccionada else None
    context = {
        "active_section": "whatsapp-conversaciones",
        "conversaciones": conversaciones[:100],
        "seleccionada": seleccionada,
        "mensajes_chat": mensajes_chat,
        "ficha": _ficha_lead(lead),
        "canales_filtro": WhatsAppChannel.objects.filter(activo=True).order_by("nombre"),
        "asesores_filtro": _asesores_activos(),
        "filtros": {
            "q": request.GET.get("q", ""),
            "state": request.GET.get("state", "all"),
            "channel": request.GET.get("channel", ""),
            "advisor": request.GET.get("advisor", ""),
        },
        "conteos": _conteos(),
    }
    return render(request, "dashboard/whatsapp_conversations.html", context)


@login_required
@whatsapp_required
@require_POST
def whatsapp_conversacion_accion(request, conversation_id):
    conversacion = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)
    accion = request.POST.get("action", "")
    try:
        if accion == "take":
            tomar_conversacion(conversacion.id, request.user)
        elif accion == "return_bot":
            devolver_al_bot(conversacion.id, request.user, request.POST.get("instruction", "esperar"))
        elif accion == "quote":
            enviar_a_cotizar(
                conversacion.id,
                request.user,
                motivo=request.POST.get("reason", "Revision solicitada por asesor"),
                datos_faltantes=conversacion.datos_faltantes,
            )
        elif accion == "close":
            cerrar_conversacion(conversacion.id, request.user)
        elif accion == "reply":
            _enviar_respuesta(conversacion, request.user, request.POST.get("message", ""))
        else:
            messages.error(request, "Accion no reconocida.")
    except (ConversacionOcupada, TransicionConversacionInvalida) as exc:
        messages.error(request, str(exc))
    except Exception:
        messages.error(request, "No se pudo completar la accion.")
    return redirect(f"{reverse('dashboard-whatsapp-conversaciones')}?conversation={conversation_id}")


def _filtrar_conversaciones(queryset, request):
    search = request.GET.get("q", "").strip()
    state = request.GET.get("state", "all")
    channel = request.GET.get("channel", "")
    advisor = request.GET.get("advisor", "")
    archived = request.GET.get("archived", "false").lower() == "true"
    # transportistas: "true" solo transportistas · "false" (default) los excluye ·
    # "all" no filtra (el frontend particiona client-side — lo usa la bandeja Vue
    # y los diálogos "Gestionar", que necesitan ver TODOS los contactos).
    transportistas_param = request.GET.get("transportistas", "false").lower()

    # Remove 24h filter - show ALL conversations
    # Frontend polls every 5 seconds anyway
    # Only filter by explicit criteria

    # Exclude test/demo clients from interface
    queryset = queryset.exclude(cliente__nombre__icontains="TEST").exclude(
        cliente__nombre__icontains="Stage"
    )

    # FASE 5B: Filter only active channels for operational bandeja
    # Seed/inactive channels excluded from normal interface
    queryset = queryset.filter(channel__activo=True)

    # Archivadas: estado del CRM, no de WhatsApp. La bandeja principal las excluye
    # por defecto; ?archived=true trae solo las archivadas (pestaña "Archivados").
    # Si el asesor busca algo desde la bandeja principal (sin pedir la pestaña
    # Archivados), la búsqueda SÍ alcanza a las archivadas — "ocultar" un contacto
    # no debe volverlo imposible de encontrar, solo sacarlo de la vista por defecto.
    if archived or not search:
        queryset = queryset.filter(archivada=archived)

    # Transportistas: contacto (Cliente.es_transportista), no conversación.
    if transportistas_param != "all":
        queryset = queryset.filter(cliente__es_transportista=transportistas_param == "true")

    if search:
        search_digits = re.sub(r"\D", "", search)
        filtro = (
            Q(cliente__nombre__icontains=search)
            | Q(cliente__display_name__icontains=search)
            | Q(cliente__channel_profile_name__icontains=search)
            | Q(cliente__telefono__icontains=search)
            | Q(cliente__phone_e164__icontains=search)
            | Q(resumen__icontains=search)
            | Q(motivo_derivacion__icontains=search)
        )
        # Buscar por número aunque el asesor escriba espacios/guiones/+
        if len(search_digits) >= 3:
            filtro |= Q(cliente__phone_e164__icontains=search_digits) | Q(cliente__telefono__icontains=search_digits)
        queryset = queryset.filter(filtro)
    state_filters = {
        "new": Q(estado_recopilacion=ConversacionWhatsApp.RECOPILACION_NUEVA),
        "bot": Q(estado_atencion=ConversacionWhatsApp.ATENCION_BOT),
        "advisor": Q(estado_atencion=ConversacionWhatsApp.ATENCION_ASESOR),
        "waiting": Q(estado_recopilacion=ConversacionWhatsApp.RECOPILACION_ESPERANDO),
        "missing": ~Q(datos_faltantes=[]),
        "quote": Q(estado_cotizacion=ConversacionWhatsApp.COTIZACION_PENDIENTE),
        "sent": Q(estado_cotizacion=ConversacionWhatsApp.COTIZACION_PRECIO_ENVIADO),
        "closed": Q(estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA),
    }
    if state in state_filters:
        queryset = queryset.filter(state_filters[state])
    if channel.isdigit():
        queryset = queryset.filter(channel_id=int(channel))
    if advisor.isdigit():
        queryset = queryset.filter(responsable_id=int(advisor))
    # Order by last activity DESC, then by ID DESC
    return queryset.order_by("-ultima_actividad", "-id")


def _seleccionar_conversacion(queryset, conversation_id):
    if conversation_id and conversation_id.isdigit():
        seleccionada = queryset.filter(pk=int(conversation_id)).first()
        if seleccionada:
            return seleccionada
    return queryset.first()


def _mensajes_para_chat(conversacion):
    if not conversacion:
        return []
    mensajes = list(conversacion.mensajes.select_related("autor", "evidencia").all())
    return [
        {
            "origen": mensaje.origen,
            "contenido": mensaje.contenido,
            "tipo": mensaje.tipo,
            "estado": mensaje.estado,
            "fecha": mensaje.fecha_mensaje,
            "evidencia": mensaje.evidencia,
        }
        for mensaje in mensajes
    ]


def _ficha_lead(lead):
    if not lead:
        return []
    values = [
        ("Tipo de servicio", lead.tipo_servicio),
        ("Origen", lead.direccion_origen or lead.distrito_origen),
        ("Destino", lead.direccion_destino or lead.distrito_destino),
        ("Piso origen", lead.piso_origen),
        ("Piso destino", lead.piso_destino),
        ("Ascensor origen", _si_no(lead.ascensor_origen)),
        ("Ascensor destino", _si_no(lead.ascensor_destino)),
        ("Fecha", lead.fecha_servicio),
        ("Horario", lead.horario_servicio),
        ("Inventario", lead.lista_objetos),
        ("Objetos especiales", lead.objetos_pesados),
        ("Embalaje", lead.modalidad_servicio),
        ("Desarmado", _si_no(lead.requiere_desarmado)),
        ("Observaciones", lead.observaciones),
    ]
    return [{"label": label, "value": value if value not in (None, "") else "Pendiente"} for label, value in values]


def _conteos():
    queryset = ConversacionWhatsApp.objects.all()
    return {
        "all": queryset.count(),
        "bot": queryset.filter(estado_atencion=ConversacionWhatsApp.ATENCION_BOT).count(),
        "advisor": queryset.filter(estado_atencion=ConversacionWhatsApp.ATENCION_ASESOR).count(),
        "quote": queryset.filter(estado_cotizacion=ConversacionWhatsApp.COTIZACION_PENDIENTE).count(),
    }


def _asesores_activos():
    from django.contrib.auth import get_user_model
    return get_user_model().objects.filter(
        Q(groups__name__in=["Administrador", "Supervisor", "Asesor de Ventas"])
        | Q(is_superuser=True),
        is_active=True,
    ).distinct().order_by("first_name", "username")


@login_required
@whatsapp_required
@csrf_exempt
def api_active_conversations(request):
    """API endpoint: traer conversaciones activas con filtros para Materio

    Incluye snapshot_cursor para SSE coherente: eventos posteriores a este
    cursor se cargarán mediante SSE, evitando repetición del historial.
    """
    try:
        from apps.whatsapp_bot_v4.models import ConversationOwnership
        from apps.whatsapp.redis_events import get_latest_cursor

        # Obtener cursor de Redis ANTES de cargar conversaciones
        snapshot_cursor = get_latest_cursor()

        # Pagination
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("limit", 25))

        if page < 1:
            page = 1
        if page_size > 100:
            page_size = 100
        if page_size < 5:
            page_size = 5

        # Filtrar (mismo código que whatsapp_conversaciones)
        conversaciones = ConversacionWhatsApp.objects.select_related(
            "cliente", "lead", "channel", "responsable"
        )
        conversaciones = _filtrar_conversaciones(conversaciones, request)

        # Total count
        total_count = conversaciones.count()

        # Apply pagination
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        conversaciones_page = conversaciones[start_idx:end_idx]

        # "Campo" (conductores/ayudantes) se auto-detecta por teléfono contra
        # Personal de campo ya registrado — no es un campo guardado en Cliente,
        # así que se calcula una vez por página, no por fila.
        from apps.campo.models import Ayudante, Conductor
        from apps.clientes.phone_identity import normalize_phone_identity

        campo_phones = {
            normalize_phone_identity(t) for t in
            list(Conductor.objects.filter(activo=True).values_list("telefono", flat=True))
            + list(Ayudante.objects.filter(activo=True).values_list("telefono", flat=True))
            if t
        }

        data = []
        for conv in conversaciones_page:
            # Obtener último mensaje eficientemente — excluye ocultos en el CRM: si el
            # oculto era el último, el preview debe caer al anterior VISIBLE.
            ultimo_mensaje = conv.mensajes.filter(oculto_en_crm=False).order_by('-fecha_mensaje').first()

            # Contar mensajes no leídos para este usuario
            from apps.whatsapp.services_read_state import get_unread_count
            unread_count = get_unread_count(conv, request.user) if request.user.is_authenticated else 0

            # Generar preview del último mensaje
            preview = _get_message_preview(ultimo_mensaje)

            # Obtener información del lead para resumen
            lead = conv.lead

            # Nombre de contacto para la bandeja. El CRM de atención necesita
            # identificar al cliente: si el nombre de perfil de WhatsApp no sirve
            # (un emoji, un ".", "R4", vacío) se manda 'name' vacío y el front
            # muestra solo el teléfono. 'profile_name' lleva siempre el nombre
            # crudo (para la búsqueda y para poder mostrarlo si el asesor quiere).
            if conv.cliente:
                profile_name = conv.cliente.profile_name
                name_usable = conv.cliente.profile_name_usable
                name_is_manual = conv.cliente.name_is_manual
                phone = conv.cliente.contact_phone
                phone_is_id = not conv.cliente.has_real_phone
            else:
                profile_name, name_usable, name_is_manual, phone, phone_is_id = '', False, False, '', False

            data.append({
                'id': conv.id,
                'name': profile_name if name_usable else '',
                'profile_name': profile_name,
                'name_usable': name_usable,
                'name_is_manual': name_is_manual,
                'phone': phone,
                'phone_is_id': phone_is_id,
                'avatar': None,  # Se genera con iniciales en el front
                'channel': {
                    'id': conv.channel.id if conv.channel else None,
                    'name': conv.channel.nombre if conv.channel else 'Desconocido',
                    'icon': _get_channel_icon(conv.channel.nombre if conv.channel else None),
                },
                'estado_atencion': conv.estado_atencion,
                'estado_cotizacion': conv.estado_cotizacion,
                'archived': conv.archivada,
                'is_transportista': conv.cliente.es_transportista if conv.cliente else False,
                'is_oficina': conv.cliente.es_oficina if conv.cliente else False,
                'is_campo': bool(conv.cliente and (
                    conv.cliente.es_campo
                    or normalize_phone_identity(conv.cliente.telefono) in campo_phones
                )),
                'preview': preview,
                'unread_count': unread_count,
                'last_activity': conv.ultima_actividad.isoformat() if conv.ultima_actividad else conv.actualizada_en.isoformat(),
                'lead_id': conv.lead.id if conv.lead else None,
                'responsable': {
                    'id': conv.responsable.id if conv.responsable else None,
                    'nombre': conv.responsable.get_full_name() or conv.responsable.username if conv.responsable else None,
                },
                'service_data': _service_data(conv),
            })

        # Response with pagination metadata and snapshot cursor for SSE coherence
        response = JsonResponse({
            'conversations': data,
            'pagination': {
                'page': page,
                'limit': page_size,
                'total': total_count,
                'pages': (total_count + page_size - 1) // page_size,
                'has_next': (page * page_size) < total_count,
                'has_prev': page > 1,
            },
            'snapshot_cursor': snapshot_cursor,  # SSE inicia desde aquí
        })

        # Disable caching to ensure fresh data
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'

        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': str(e),
            'type': type(e).__name__,
            'conversations': [],
            'pagination': {'page': 1, 'limit': 0, 'total': 0, 'pages': 0},
        }, status=400)


def _enviar_respuesta(conversacion, actor, contenido):
    contenido = contenido.strip()
    if not contenido:
        raise TransicionConversacionInvalida("Escribe un mensaje.")
    conversacion = tomar_conversacion(conversacion.id, actor)

    # PAUSA BOT: asesor tiene control (desde CRM)
    from apps.whatsapp_bot_v4.models import ConversationOwnership
    ownership, _ = ConversationOwnership.objects.get_or_create(conversation=conversacion)
    ownership.owner_type = ConversationOwnership.OWNER_ADVISOR
    ownership.control_mode = ConversationOwnership.MODE_MANUAL
    ownership.advisor_id = actor
    ownership.last_human_message_at = timezone.now()
    ownership.save()

    # 1. GUARDAR EN BD PRIMERO (para que aparezca inmediatamente en el chat)
    mensaje = MensajeWhatsApp.objects.create(
        conversacion=conversacion,
        direccion=MensajeWhatsApp.SALIENTE,
        origen=MensajeWhatsApp.ORIGEN_ASESOR,
        tipo="texto",
        contenido=contenido,
        autor=actor,
        estado="enviando",  # Estado temporal
        error_detalle="",
    )

    # 2. ENVIAR A WHATSAPP (Meta o YCloud)
    resultado = send_whatsapp_message(
        conversacion.cliente.telefono,
        contenido,
        channel=conversacion.channel,
    )

    # 3. ACTUALIZAR ESTADO SEGÚN RESULTADO
    meta_id = ""
    if isinstance(resultado, dict):
        if resultado.get("sent"):  # YCloud
            meta_id = resultado.get("id", "")
            mensaje.estado = "enviado"
        elif resultado.get("messages"):  # Meta
            meta_id = resultado["messages"][0].get("id", "")
            mensaje.estado = "enviado"
        else:  # Error
            error_msg = resultado.get("reason", "Error al enviar")
            mensaje.estado = "error"
            mensaje.error_detalle = error_msg
    else:
        mensaje.estado = "error"
        mensaje.error_detalle = "Respuesta inválida del servidor"

    if meta_id:
        mensaje.meta_message_id = meta_id

    mensaje.save()

    ConversacionLegacy.objects.create(cliente=conversacion.cliente, mensaje_salida=contenido)
    conversacion.ultimo_mensaje_enviado = timezone.now()
    conversacion.ultima_actividad = timezone.now()
    conversacion.save(update_fields=["ultimo_mensaje_enviado", "ultima_actividad", "actualizada_en"])
    if mensaje.estado == "error":
        raise TransicionConversacionInvalida("Meta no confirmo el envio; mensaje registrado con error.")
    return mensaje


def _map_mensaje_origen_to_sender(origen):
    """Map MensajeWhatsApp origen to Vue component sender type"""
    origen_map = {
        MensajeWhatsApp.ORIGEN_CLIENTE: 'client',
        MensajeWhatsApp.ORIGEN_BOT: 'bot',
        MensajeWhatsApp.ORIGEN_ASESOR: 'advisor',
        'sistema': 'system',
    }
    return origen_map.get(origen, 'system')


def _get_channel_icon(channel_name):
    """Map channel names to Remixicon icons"""
    if not channel_name:
        return "global-line"
    channel_map = {
        "WhatsApp": "whatsapp-line",
        "Correo": "mail-line",
        "Instagram": "instagram-line",
        "Facebook": "facebook-circle-line",
        "Chat web": "chat-3-line",
        "TikTok": "tiktok-line",
    }
    return channel_map.get(channel_name, "global-line")


def _service_data(conv):
    """Datos de servicio para el panel derecho de la bandeja.

    Se lee del Lead si existe; si aún no hay Lead, de conversacion.datos_extraidos
    (lo que la extracción NLU haya detectado). Así el panel muestra origen/destino
    en cuanto se detectan, sin esperar a que se cree el Lead."""
    lead = conv.lead
    ex = conv.datos_extraidos or {}
    if not lead and not ex:
        return None

    def _texto(attr, ex_key=None):
        if lead:
            v = getattr(lead, attr, None)
            if v not in (None, ""):
                return v
        return ex.get(ex_key or attr) or None

    def _num(attr):
        if lead and getattr(lead, attr, None) is not None:
            return getattr(lead, attr)
        v = ex.get(attr)
        return v if isinstance(v, int) else None

    def _bool(attr):
        if lead and getattr(lead, attr, None) is not None:
            return getattr(lead, attr)
        v = ex.get(attr)
        return v if isinstance(v, bool) else None

    fecha = None
    if lead and lead.fecha_servicio:
        fecha = lead.fecha_servicio.isoformat()
    else:
        fecha = ex.get("fecha_servicio") or ex.get("fecha_texto") or None

    def _numish(attr):
        if lead and getattr(lead, attr, None) is not None:
            return getattr(lead, attr)
        v = ex.get(attr)
        return v if isinstance(v, (int, float)) else None

    # Servicios extra contratados (personal, embalaje, desarmado/armado).
    extra_services = []
    if lead:
        if lead.incluye_personal_carga:
            n = lead.cantidad_operarios
            extra_services.append(f"Personal de carga ({n})" if n else "Personal de carga")
        if lead.modalidad_servicio:
            extra_services.append(f"Embalaje: {lead.modalidad_servicio}")
        if lead.requiere_desarmado:
            extra_services.append("Desarmado de muebles")
        if lead.requiere_armado:
            extra_services.append("Armado de muebles")

    # Precio sugerido (motor) + precio cotizado (lo ya enviado al cliente).
    # Misma función que usa el modal de Cotizar → los dos muestran igual número.
    from apps.cotizador.pricing import panel_prices
    suggested, quoted = panel_prices(lead)

    cli = conv.cliente
    return {
        "customer_name": (cli.nombre or cli.profile_name or "") if cli else "",
        "customer_phone": (cli.contact_phone or "") if cli else "",
        "contact_name": (lead.persona_contacto or "") if lead else "",
        "contact_phone": (lead.telefono_contacto or "") if lead else "",
        "type": _texto("tipo_servicio"),
        "origin": _texto("distrito_origen"),
        "destination": _texto("distrito_destino"),
        "address_origin": _texto("direccion_origen"),
        "address_destination": _texto("direccion_destino"),
        "floor_origin": _num("piso_origen"),
        "floor_destination": _num("piso_destino"),
        "elevator_origin": _bool("ascensor_origen"),
        "elevator_destination": _bool("ascensor_destino"),
        "items": _texto("lista_objetos"),
        "heavy_items": _texto("objetos_pesados"),
        "weight_kg": _numish("peso_carga_kg"),
        "volume_m3": _numish("volumen_carga_m3"),
        "extra_services": extra_services,
        "date": fecha,
        "schedule": _texto("horario_servicio"),
        "status": _get_cotizacion_status(conv.estado_cotizacion),
        "estado_cotizacion": conv.estado_cotizacion,
        "information_pct": conv.porcentaje_informacion or 0,
        "is_interprovincial": bool(lead.es_interprovincial) if lead else bool(ex.get("es_interprovincial")),
        "price": quoted or suggested or None,
        "suggested_price": suggested,
        "quoted_price": quoted,
        # Precio negociado que la IA detectó en el chat (referencia, editable).
        "chat_price": ex.get("precio_chat"),
        "chat_price_accepted": bool(ex.get("precio_chat_aceptado")),
        "chat_price_includes": ex.get("precio_chat_incluye"),
        "chat_price_note": ex.get("precio_chat_condiciones"),
        "has_lead": bool(lead),
    }


def _get_cotizacion_status(estado_cotizacion):
    """Map cotización states to display names"""
    status_map = {
        ConversacionWhatsApp.COTIZACION_SIN_INICIAR: "Sin cotizar",
        ConversacionWhatsApp.COTIZACION_PENDIENTE: "Por cotizar",
        ConversacionWhatsApp.COTIZACION_PRECIO_ENVIADO: "Precio enviado",
        ConversacionWhatsApp.COTIZACION_CERRADA: "Cerrada",
    }
    return status_map.get(estado_cotizacion, "Desconocido")


def _si_no(value):
    if value is None:
        return "Pendiente"
    return "Si" if value else "No"


# Backend estado (Spanish, DB-canonical) -> frontend status (English, canonical contract)
ESTADO_TO_STATUS = {
    'recibido': 'received',
    'pendiente': 'sending',
    'enviado': 'sent',
    'entregado': 'delivered',
    'leido': 'read',
    'error': 'failed',
}


def _sender_name_and_badge(msg, conversation):
    """Shared sender-name/badge resolution — used for the message itself and for
    a quoted reply preview, so both always agree."""
    if msg.sender_type == MensajeWhatsApp.SENDER_CUSTOMER:
        return (conversation.cliente.nombre if conversation.cliente else 'Cliente'), None
    if msg.sender_type == MensajeWhatsApp.SENDER_BOT:
        return 'TaxiCarga Bot', 'bot'
    if msg.sender_type == MensajeWhatsApp.SENDER_ADVISOR:
        if msg.source == MensajeWhatsApp.SOURCE_WHATSAPP_BUSINESS_APP:
            return 'Atención humana desde WhatsApp', 'whatsapp'
        return (msg.autor.get_full_name() or msg.autor.username if msg.autor else 'Asesor'), 'crm'
    return 'Sistema', 'system'


def _reply_preview(msg, conversation):
    """Small denormalized preview of the quoted message for the reply UI —
    enough to render a WhatsApp-style quote block without a second fetch."""
    if not msg.responde_a_id:
        return None
    quoted = msg.responde_a
    sender_name, _badge = _sender_name_and_badge(quoted, conversation)
    if quoted.tipo in ('imagen', 'audio', 'video', 'documento'):
        preview_text = quoted.caption or f'[{quoted.tipo}]'
    else:
        preview_text = quoted.contenido[:120]

    return {
        'id': quoted.id,
        'senderName': sender_name,
        'type': quoted.tipo if quoted.tipo != 'texto' else 'text',
        'text': preview_text,
    }


def _serialize_mensaje(msg, conversation):
    """Canonical message JSON shape — single source of truth.

    Reused by conversation_messages() (list) and api_send_message() (single message),
    so both endpoints and the SSE payload contract stay in sync.
    """
    sender_type = msg.sender_type or _map_mensaje_origen_to_sender(msg.origen)
    source = msg.source or "unknown"
    sender_name, badge = _sender_name_and_badge(msg, conversation)

    mensaje_type = 'text'
    adjuntos_data = []
    if msg.tipo in ('imagen', 'audio', 'video', 'documento'):
        mensaje_type = msg.tipo
        for adjunto in msg.adjuntos.all():
            adjunto_dict = {
                'id': adjunto.id,
                'type': adjunto.formato,
                'media_id': adjunto.ycloud_media_id,
                'mime_type': adjunto.mime_type,
                'filename': adjunto.filename,
                'file_size': adjunto.file_size,
                'sha256': adjunto.sha256,
            }
            # Always serve through the authenticated proxy — MEDIA_ROOT is private
            # (datos_privados/media) and not exposed by nginx or any Django urlpattern,
            # so adjunto.archivo.url would point nowhere servable.
            adjunto_dict['url'] = f'/media/proxy/{adjunto.ycloud_media_id}/'
            adjuntos_data.append(adjunto_dict)

        if not adjuntos_data and msg.ycloud_media_id:
            adjuntos_data.append({
                'id': None,
                'type': mensaje_type,
                'media_id': msg.ycloud_media_id,
                'mime_type': msg.mime_type or 'application/octet-stream',
                'filename': msg.filename or f'{mensaje_type}-{msg.id}',
                'file_size': msg.file_size or 0,
                'sha256': msg.sha256 or '',
                'url': f'/media/proxy/{msg.ycloud_media_id}/',
            })

    return {
        'id': msg.id,
        'sender': msg.sender_type or 'unknown',
        'senderName': sender_name,
        'source': source,
        'badge': badge,
        'type': mensaje_type,
        'text': msg.contenido,
        'caption': msg.caption or None,
        'attachments': adjuntos_data if adjuntos_data else None,
        'timestamp': msg.fecha_mensaje.isoformat(),
        'status': ESTADO_TO_STATUS.get(msg.estado, msg.estado),
        'errorDetail': msg.error_detalle or None,
        'avatar': None,
        # Only messages with a real wamid can be quote-replied to — YCloud's
        # context.message_id requires it. Frontend uses this to enable/disable
        # the reply action per-bubble instead of failing at send time.
        # NOTE: sourced from wamid (real WhatsApp/Meta id), not meta_message_id (YCloud's
        # internal id) — only wamid works as context.message_id when quoting this message.
        'metaMessageId': msg.wamid or None,
        'replyTo': _reply_preview(msg, conversation),
        'reactionEmoji': msg.reaction_emoji or None,
    }


@login_required
@whatsapp_required
def conversation_messages(request, conversation_id):
    """Endpoint para traer mensajes de conversación con info completa (polling en vivo)"""
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)

    # Mark conversation as read for this user
    from apps.whatsapp.services_read_state import mark_conversation_as_read
    mark_conversation_as_read(conversation, request.user)
    messages = MensajeWhatsApp.objects.filter(
        conversacion=conversation, oculto_en_crm=False
    ).select_related('autor', 'responde_a', 'responde_a__autor').prefetch_related('adjuntos').order_by('fecha_mensaje')

    messages_list = [_serialize_mensaje(msg, conversation) for msg in messages]

    logger.info(f"conversation_messages: {conversation_id} → {len(messages_list)} mensajes")

    return JsonResponse({
        'messages': messages_list,
        'total': len(messages_list),
        'conversation_id': conversation_id,
    })


@login_required
@whatsapp_required
def api_unread_counts(request):
    """Get unread message counts for all conversations for the current user"""
    from apps.whatsapp.services_read_state import get_unread_conversations

    unread_map = get_unread_conversations(request.user)

    return JsonResponse({
        'unread': unread_map,
        'total_unread': sum(unread_map.values()),
    })


@login_required
@whatsapp_required
def pause_bot(request, conversation_id):
    """Asesor está escribiendo, pausar bot"""
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)
    from apps.whatsapp_bot_v4.models import ConversationOwnership
    ownership, created = ConversationOwnership.objects.get_or_create(
        conversation=conversation
    )
    ownership.owner_type = ConversationOwnership.OWNER_ADVISOR
    ownership.advisor_id = request.user
    ownership.control_mode = ConversationOwnership.MODE_MANUAL
    ownership.save()
    logger.info(f"Bot paused by advisor {request.user.id} for conversation {conversation_id}")
    return JsonResponse({'status': 'paused'})


@login_required
@whatsapp_required
def resume_bot(request, conversation_id):
    """Asesor terminó, reactivar bot"""
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)
    from apps.whatsapp_bot_v4.models import ConversationOwnership
    ownership, created = ConversationOwnership.objects.get_or_create(
        conversation=conversation
    )
    ownership.owner_type = ConversationOwnership.OWNER_BOT
    ownership.advisor_id = None
    ownership.save()
    logger.info(f"Bot reactivated for conversation {conversation_id}")
    return JsonResponse({'status': 'active'})


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_crear_conversacion_manual(request):
    """El asesor escribe un número que nunca contactó y arranca la conversación
    desde cero — no viene de un webhook. Ver crear_conversacion_manual()."""
    from apps.whatsapp.domain import TransicionConversacionInvalida, crear_conversacion_manual

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}
    telefono = body.get("telefono") or request.POST.get("telefono", "")
    nombre = body.get("nombre") or request.POST.get("nombre", "")

    try:
        conversacion = crear_conversacion_manual(telefono, request.user, nombre=nombre)
    except TransicionConversacionInvalida as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse({"status": "ok", "conversation_id": conversacion.id})


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def mark_conversation_read(request, conversation_id):
    """Mark conversation as read for the current user"""
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)
    from apps.whatsapp.services_read_state import mark_conversation_as_read
    mark_conversation_as_read(conversation, request.user)
    return JsonResponse({'status': 'marked_read'})


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_send_message(request, conversation_id):
    """JSON endpoint for the SPA composer — advisor manual reply.

    Contract:
      POST body (JSON): {"message": str, "client_msg_id": str (optional, echoed back)}
      200 -> {"success": true, "clientMsgId", "message": <_serialize_mensaje shape>}
      400 -> {"success": false, "error_code": "empty_message"|"invalid_json", "error_detail": str}
      409 -> {"success": false, "error_code": "conversation_locked", "error_detail": str}
      502 -> {"success": false, "clientMsgId", "message": <_serialize_mensaje shape>,
              "error_code": str, "error_detail": str}
              (502 = YCloud/upstream failed to accept the message; the failed attempt
              is still persisted and returned so the advisor sees it and can retry)
    """
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse(
            {"success": False, "error_code": "invalid_json", "error_detail": "Cuerpo de la petición inválido."},
            status=400,
        )

    contenido = (data.get("message") or "").strip()
    client_msg_id = data.get("client_msg_id", "")
    reply_to_id = data.get("reply_to_id")

    if not contenido:
        return JsonResponse(
            {"success": False, "error_code": "empty_message", "error_detail": "Escribe un mensaje."},
            status=400,
        )

    reply_to = None
    if reply_to_id:
        reply_to = MensajeWhatsApp.objects.filter(
            id=reply_to_id, conversacion=conversation
        ).first()
        if not reply_to:
            return JsonResponse(
                {"success": False, "error_code": "reply_target_not_found", "error_detail": "El mensaje citado no existe."},
                status=400,
            )

    try:
        conversation = tomar_conversacion(conversation.id, request.user)
    except (ConversacionOcupada, TransicionConversacionInvalida) as exc:
        return JsonResponse(
            {"success": False, "error_code": "conversation_locked", "error_detail": str(exc)},
            status=409,
        )

    # Advisor takes manual control (mirrors legacy _enviar_respuesta)
    from apps.whatsapp_bot_v4.models import ConversationOwnership
    ownership, _ = ConversationOwnership.objects.get_or_create(conversation=conversation)
    ownership.owner_type = ConversationOwnership.OWNER_ADVISOR
    ownership.control_mode = ConversationOwnership.MODE_MANUAL
    ownership.advisor_id = request.user
    ownership.last_human_message_at = timezone.now()
    ownership.save()

    result = send_crm_message(conversation, request.user, contenido, reply_to=reply_to)
    mensaje = result["message"]

    if mensaje:
        conversation.ultimo_mensaje_enviado = timezone.now()
        conversation.ultima_actividad = timezone.now()
        conversation.save(update_fields=["ultimo_mensaje_enviado", "ultima_actividad", "actualizada_en"])

    payload = {
        "success": result["success"],
        "clientMsgId": client_msg_id,
        "message": _serialize_mensaje(mensaje, conversation) if mensaje else None,
        "error_code": result["error_code"],
        "error_detail": result["error_detail"],
    }
    # No message row means the request was rejected before we even tried to send
    # (e.g. replying to a message without a wamid) — that's a client error (400),
    # distinct from 502 (we tried, YCloud/upstream rejected it).
    if result["success"]:
        status_code = 200
    elif mensaje is None:
        status_code = 400
    else:
        status_code = 502

    return JsonResponse(payload, status=status_code)


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_react_message(request, conversation_id, message_id):
    """React to a message from the CRM (WhatsApp-style emoji reaction on a bubble).

    Contract:
      POST body (JSON): {"emoji": str}  ("" removes the current reaction)
      200 -> {"success": true, "reactionEmoji": str|null}
      400 -> {"success": false, "error_code": "reaction_target_no_wamid"|..., "error_detail": str}
      404 -> message not found in this conversation
      502 -> {"success": false, "error_code": str, "error_detail": str} (YCloud rejected it)
    """
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)
    target_message = get_object_or_404(MensajeWhatsApp, pk=message_id, conversacion=conversation)

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse(
            {"success": False, "error_code": "invalid_json", "error_detail": "Cuerpo de la petición inválido."},
            status=400,
        )

    emoji = data.get("emoji", "")

    from apps.whatsapp.services import send_crm_reaction
    result = send_crm_reaction(conversation, target_message, emoji)

    if result["success"]:
        return JsonResponse({"success": True, "reactionEmoji": emoji or None}, status=200)

    status_code = 400 if result["error_code"] in ("reaction_target_no_wamid", "ycloud_unavailable") else 502
    return JsonResponse(
        {"success": False, "error_code": result["error_code"], "error_detail": result["error_detail"]},
        status=status_code,
    )


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_hide_message(request, conversation_id, message_id):
    """'Ocultar en el CRM' — never deletes the row (messages are commercial evidence
    for quotes). Hides it from the timeline and bandeja preview for EVERY CRM user
    (shared inbox, not per-advisor), records who/when, and publishes it live so any
    other session with this conversation open drops it without a reload.

    Contract:
      POST (no body needed)
      200 -> {"success": true}
      404 -> message not found in this conversation
    """
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)
    message = get_object_or_404(MensajeWhatsApp, pk=message_id, conversacion=conversation)

    if not message.oculto_en_crm:
        message.oculto_en_crm = True
        message.oculto_por = request.user
        message.oculto_en = timezone.now()
        message.save(update_fields=["oculto_en_crm", "oculto_por", "oculto_en"])

        from apps.whatsapp.signals import publish_message_media_ready
        publish_message_media_ready(message)

    return JsonResponse({"success": True})


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_archive_conversation(request, conversation_id):
    """Archive a conversation — CRM-only state, doesn't touch WhatsApp at all.
    No confirmation needed (low-risk, reversible). Publishes conversation.updated
    (via the existing significant-fields signal) so it drops out of every open
    session's main bandeja live, without a reload.
    """
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)

    if not conversation.archivada:
        conversation.archivada = True
        conversation.archivada_por = request.user
        conversation.archivada_en = timezone.now()
        conversation.save(update_fields=["archivada", "archivada_por", "archivada_en"])

    return JsonResponse({"success": True})


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_unarchive_conversation(request, conversation_id):
    """Manual unarchive (from the Archivados tab). See also: automatic unarchive on
    a new inbound customer message, in services_ycloud.py's process_ycloud_event —
    same WhatsApp behavior, triggered from the webhook instead of this endpoint.
    """
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)

    if conversation.archivada:
        conversation.archivada = False
        conversation.archivada_por = None
        conversation.archivada_en = None
        conversation.save(update_fields=["archivada", "archivada_por", "archivada_en"])

    return JsonResponse({"success": True})


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_set_transportista(request, conversation_id):
    """Marcar/desmarcar es_transportista a mano, desde la ficha del contacto o
    el menú de la conversación. Es la vía de reversión obligatoria: la marca
    automática (Fase 2, por código OFERTA-<código>) es pegajosa a propósito,
    así que sin esto un cliente real marcado por error queda atrapado.

    Contract:
      POST body (JSON): {"es_transportista": bool}
      200 -> {"success": true, "es_transportista": bool}
    """
    conversation = get_object_or_404(
        ConversacionWhatsApp.objects.select_related("cliente"), pk=conversation_id
    )
    if not conversation.cliente:
        return JsonResponse({"success": False, "error": "Conversación sin cliente."}, status=409)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON inválido."}, status=400)

    nuevo_valor = bool(payload.get("es_transportista"))

    from apps.tercerizacion.services import marcar_transportista, desmarcar_transportista
    from apps.whatsapp.signals import publish_transportista_state_change

    if nuevo_valor:
        marcar_transportista(conversation.cliente, usuario=request.user)
    else:
        desmarcar_transportista(conversation.cliente, usuario=request.user)

    publish_transportista_state_change(conversation)

    return JsonResponse({"success": True, "es_transportista": conversation.cliente.es_transportista})


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_set_oficina(request, conversation_id):
    """Marcar/desmarcar a mano que este contacto es personal de oficina (para
    la partición 'Oficina' de la bandeja) — siempre manual, a diferencia de
    'Campo' que se auto-detecta por teléfono contra Conductor/Ayudante.

    Contract:
      POST body (JSON): {"es_oficina": bool}
      200 -> {"success": true, "es_oficina": bool}
    """
    conversation = get_object_or_404(
        ConversacionWhatsApp.objects.select_related("cliente"), pk=conversation_id
    )
    if not conversation.cliente:
        return JsonResponse({"success": False, "error": "Conversación sin cliente."}, status=409)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON inválido."}, status=400)

    conversation.cliente.es_oficina = bool(payload.get("es_oficina"))
    conversation.cliente.save(update_fields=["es_oficina"])

    return JsonResponse({"success": True, "es_oficina": conversation.cliente.es_oficina})


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_set_campo(request, conversation_id):
    """Marcar/desmarcar a mano que este contacto es personal de campo, además
    de la detección automática por teléfono (Conductor/Ayudante activo) que
    sigue corriendo igual — esto es un refuerzo manual para el caso de
    alguien que todavía no está registrado con ese teléfono exacto.

    Contract:
      POST body (JSON): {"es_campo": bool}
      200 -> {"success": true, "es_campo": bool}
    """
    conversation = get_object_or_404(
        ConversacionWhatsApp.objects.select_related("cliente"), pk=conversation_id
    )
    if not conversation.cliente:
        return JsonResponse({"success": False, "error": "Conversación sin cliente."}, status=409)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON inválido."}, status=400)

    conversation.cliente.es_campo = bool(payload.get("es_campo"))
    conversation.cliente.save(update_fields=["es_campo"])

    return JsonResponse({"success": True, "es_campo": conversation.cliente.es_campo})


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_set_contact_name(request, conversation_id):
    """Editar a mano el nombre del contacto en el CRM, como en la agenda del
    teléfono. El nombre manual tiene prioridad sobre el de perfil de WhatsApp y
    NO se sobrescribe al llegar mensajes nuevos (services_ycloud.py ya respeta
    name_source != 'manual' antes de pisar el nombre).

    Contract:
      POST body (JSON): {"name": str}   — vacío o solo espacios => vuelve al
                                          nombre de perfil de WhatsApp
      200 -> {"success": true, "name": str, "profile_name": str,
              "name_usable": bool, "name_source": str}
      409 -> conversación sin cliente
    """
    conversation = get_object_or_404(
        ConversacionWhatsApp.objects.select_related("cliente"), pk=conversation_id
    )
    cliente = conversation.cliente
    if not cliente:
        return JsonResponse({"success": False, "error": "Conversación sin cliente."}, status=409)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON inválido."}, status=400)

    nuevo_nombre = (payload.get("name") or "").strip()[:160]

    if nuevo_nombre:
        # Conserva el nombre anterior (de WhatsApp) como alias, para poder
        # seguir encontrando el contacto buscando por él.
        anterior = (cliente.channel_profile_name or cliente.display_name or "").strip()
        if anterior and anterior != nuevo_nombre and anterior not in (cliente.aliases or []):
            cliente.aliases = (cliente.aliases or []) + [anterior]
        cliente.display_name = nuevo_nombre
        cliente.name_source = cliente.SOURCE_MANUAL
    else:
        # Revertir al nombre de perfil de WhatsApp
        cliente.display_name = (cliente.channel_profile_name or "").strip()
        cliente.name_source = cliente.SOURCE_CHANNEL if cliente.channel_profile_name else cliente.SOURCE_FALLBACK

    cliente.save(update_fields=["display_name", "name_source", "aliases"])

    from apps.whatsapp.signals import publish_contact_name_change
    publish_contact_name_change(conversation)

    return JsonResponse({
        "success": True,
        "name": cliente.profile_name if cliente.profile_name_usable else "",
        "profile_name": cliente.profile_name,
        "name_usable": cliente.profile_name_usable,
        "name_source": cliente.name_source,
    })


_RESPUESTAS_RAPIDAS_DEFAULT = {
    "respuesta": [
        "Entendido, en breve me comunico",
        "Gracias por tu consulta",
        "Te envío la cotización al WhatsApp",
        "Necesito confirmar algunos datos",
        "La cotización está lista",
        "¿En qué te puedo ayudar?",
    ],
    "cotizacion": [
        "El costo de su servicio es de S/ {precio}. Incluye transporte, carga y descarga.",
        "Su cotización: S/ {precio} (transporte + carga + descarga). Válida por 7 días.",
        "El precio del servicio es S/ {precio}, todo incluido. ¿Confirmamos la reserva?",
    ],
    "recotizacion": [
        "Le ajusto el precio: ahora queda en S/ {precio}, todo incluido (transporte, carga y descarga).",
        "Revisé su caso y le puedo dejar el servicio en S/ {precio}. ¿Lo confirmamos?",
        "Nuevo precio: S/ {precio}. Incluye transporte, carga y descarga.",
    ],
}


@login_required
@whatsapp_required
@require_http_methods(["GET", "POST"])
@csrf_exempt
def api_respuestas_rapidas(request):
    """Mensajes predefinidos — propios de cada asesor.

    ?tipo=respuesta (default) -> rayo del composer.
    ?tipo=cotizacion          -> diálogo "Cotizar" (se le inserta el precio en {precio}).

    GET  -> {"items": ["texto", ...]}  (si nunca configuró ese tipo, siembra los default)
    POST {"items": [...], "tipo": "..."} -> reemplaza toda la lista de ese tipo (máx 40, 500 c/u)
    """
    from apps.whatsapp.models import RespuestaRapida

    if request.method == "GET":
        tipo = request.GET.get("tipo", "respuesta")
        if tipo not in _RESPUESTAS_RAPIDAS_DEFAULT:
            tipo = "respuesta"
        qs = list(
            RespuestaRapida.objects.filter(usuario=request.user, tipo=tipo)
            .values_list("texto", flat=True)
        )
        if not qs:
            defaults = _RESPUESTAS_RAPIDAS_DEFAULT[tipo]
            RespuestaRapida.objects.bulk_create([
                RespuestaRapida(usuario=request.user, tipo=tipo, texto=t, orden=i)
                for i, t in enumerate(defaults)
            ])
            qs = list(defaults)
        return JsonResponse({"items": qs})

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido."}, status=400)

    tipo = payload.get("tipo", "respuesta")
    if tipo not in _RESPUESTAS_RAPIDAS_DEFAULT:
        tipo = "respuesta"
    items = [str(t).strip()[:500] for t in (payload.get("items") or []) if str(t).strip()][:40]
    with transaction.atomic():
        RespuestaRapida.objects.filter(usuario=request.user, tipo=tipo).delete()
        RespuestaRapida.objects.bulk_create([
            RespuestaRapida(usuario=request.user, tipo=tipo, texto=t, orden=i)
            for i, t in enumerate(items)
        ])
    return JsonResponse({"items": items})


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_set_transportista_bot_pausado(request, conversation_id):
    """Silencia/reactiva el bot de transportistas SOLO para esta conversación
    — independiente del interruptor global (apps/tercerizacion, bot/pausar/)
    y del pausado general del sistema. Útil si el bot se traba con un
    transportista en particular sin querer apagarlo para todos.

    Contract:
      POST body (JSON): {"pausado": bool}
      200 -> {"success": true, "pausado": bool}
    """
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON inválido."}, status=400)

    nuevo_valor = bool(payload.get("pausado"))

    from apps.tercerizacion.models import TransportistaBotState
    state, _ = TransportistaBotState.objects.get_or_create(conversacion=conversation)
    state.pausado = nuevo_valor
    state.save(update_fields=["pausado", "actualizado_en"])

    return JsonResponse({"success": True, "pausado": state.pausado})


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_forward_message(request, conversation_id, message_id):
    """Forward a message (text or media) to a DIFFERENT conversation, WhatsApp
    Web-style. Sent as a completely normal new message in the target conversation.

    Contract:
      POST body (JSON): {"target_conversation_id": int}
      200 -> {"success": true, "message": <_serialize_mensaje shape, target conv>}
      400 -> {"success": false, "error_code": str, "error_detail": str}
      404 -> source message or target conversation not found
      502 -> {"success": false, "error_code": str, "error_detail": str} (YCloud rejected it)
    """
    source_conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)
    source_message = get_object_or_404(MensajeWhatsApp, pk=message_id, conversacion=source_conversation)

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse(
            {"success": False, "error_code": "invalid_json", "error_detail": "Cuerpo de la petición inválido."},
            status=400,
        )

    target_conversation_id = data.get("target_conversation_id")
    if not target_conversation_id:
        return JsonResponse(
            {"success": False, "error_code": "missing_target", "error_detail": "Selecciona una conversación destino."},
            status=400,
        )

    target_conversation = get_object_or_404(ConversacionWhatsApp, pk=target_conversation_id)

    from apps.whatsapp.services import send_crm_forward_message
    result = send_crm_forward_message(target_conversation, request.user, source_message)
    mensaje = result["message"]

    if mensaje:
        target_conversation.ultimo_mensaje_enviado = timezone.now()
        target_conversation.ultima_actividad = timezone.now()
        target_conversation.save(update_fields=["ultimo_mensaje_enviado", "ultima_actividad", "actualizada_en"])

    payload = {
        "success": result["success"],
        "message": _serialize_mensaje(mensaje, target_conversation) if mensaje else None,
        "error_code": result["error_code"],
        "error_detail": result["error_detail"],
    }
    if result["success"]:
        status_code = 200
    elif mensaje is None:
        status_code = 400
    else:
        status_code = 502

    return JsonResponse(payload, status=status_code)


@login_required
@whatsapp_required
@require_http_methods(["POST"])
def api_send_media_message(request, conversation_id):
    """JSON endpoint for the SPA composer — advisor outbound media (image/video/audio/document).

    Contract:
      POST body (multipart/form-data): file, type ('imagen'|'video'|'audio'|'documento'),
                                        caption (optional), client_msg_id (optional)
      200 -> {"success": true, "clientMsgId", "message": <_serialize_mensaje shape>}
      400 -> {"success": false, "error_code": "no_file"|"invalid_type", "error_detail": str}
      409 -> {"success": false, "error_code": "conversation_locked", "error_detail": str}
      502 -> upstream (YCloud) failed; failed attempt still persisted, same shape as 200
    """
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)

    uploaded_file = request.FILES.get("file")
    tipo = request.POST.get("type", "")
    caption = (request.POST.get("caption") or "").strip() or None
    client_msg_id = request.POST.get("client_msg_id", "")

    if not uploaded_file:
        return JsonResponse(
            {"success": False, "error_code": "no_file", "error_detail": "No se recibió ningún archivo."},
            status=400,
        )

    if tipo not in ("imagen", "video", "audio", "documento"):
        return JsonResponse(
            {"success": False, "error_code": "invalid_type", "error_detail": "Tipo de archivo inválido."},
            status=400,
        )

    try:
        conversation = tomar_conversacion(conversation.id, request.user)
    except (ConversacionOcupada, TransicionConversacionInvalida) as exc:
        return JsonResponse(
            {"success": False, "error_code": "conversation_locked", "error_detail": str(exc)},
            status=409,
        )

    from apps.whatsapp_bot_v4.models import ConversationOwnership
    ownership, _ = ConversationOwnership.objects.get_or_create(conversation=conversation)
    ownership.owner_type = ConversationOwnership.OWNER_ADVISOR
    ownership.control_mode = ConversationOwnership.MODE_MANUAL
    ownership.advisor_id = request.user
    ownership.last_human_message_at = timezone.now()
    ownership.save()

    result = send_crm_media_message(conversation, request.user, tipo, uploaded_file, caption=caption)
    mensaje = result["message"]

    if mensaje:
        conversation.ultimo_mensaje_enviado = timezone.now()
        conversation.ultima_actividad = timezone.now()
        conversation.save(update_fields=["ultimo_mensaje_enviado", "ultima_actividad", "actualizada_en"])

    payload = {
        "success": result["success"],
        "clientMsgId": client_msg_id,
        "message": _serialize_mensaje(mensaje, conversation) if mensaje else None,
        "error_code": result["error_code"],
        "error_detail": result["error_detail"],
    }
    return JsonResponse(payload, status=200 if result["success"] else 502)


@login_required
def api_events_stream(request):
    """FASE 5B: Fallback REST polling endpoint for events.

    Used when SSE is not available or as reconciliation source.
    Cursor-based pagination using Redis Stream IDs.
    Same authorization as SSE: filtered by active channels.

    Query params:
        - cursor: Last event ID seen (default=0, means all events)

    Response:
        {
            "events": [
                {"id": "...", "type": "message.created", "timestamp": "2026-08-21T...", "data": {...}},
                ...
            ],
            "latest_cursor": "..."
        }
    """
    from apps.dashboard.permissions import can_manage_whatsapp
    from apps.whatsapp.redis_events import get_events, get_latest_cursor
    from apps.whatsapp.models import WhatsAppChannel

    # Check authorization (same as SSE)
    if not can_manage_whatsapp(request.user):
        raise PermissionDenied("No tienes permisos para acceder a eventos de WhatsApp")

    # Get authorized channels
    authorized_channels = set(
        WhatsAppChannel.objects.filter(activo=True).values_list('id', flat=True)
    )

    cursor = request.GET.get('cursor', '0')

    # Get events from Redis Stream
    all_events = get_events(cursor=cursor)

    # Filter by authorized channels
    filtered_events = [
        e for e in all_events
        if e.data.get('channel_id') in authorized_channels
    ]

    latest_cursor = get_latest_cursor()

    return JsonResponse({
        'events': [e.to_dict() for e in filtered_events],
        'latest_cursor': latest_cursor,
        'timestamp': timezone.now().isoformat()
    })
