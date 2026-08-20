from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import logging

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
from apps.whatsapp.services import send_whatsapp_message


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
    from datetime import timedelta
    search = request.GET.get("q", "").strip()
    state = request.GET.get("state", "all")
    channel = request.GET.get("channel", "")
    advisor = request.GET.get("advisor", "")

    # Filtrar últimas 24h (como polling)
    queryset = queryset.filter(
        creada_en__gte=timezone.now() - timedelta(hours=24)
    )

    if search:
        queryset = queryset.filter(
            Q(cliente__nombre__icontains=search)
            | Q(cliente__telefono__icontains=search)
            | Q(resumen__icontains=search)
            | Q(motivo_derivacion__icontains=search)
        )
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
    return queryset.order_by("-actualizada_en", "-id")


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


@csrf_exempt
def api_active_conversations(request):
    """API endpoint: traer conversaciones activas con filtros para Materio"""
    from datetime import timedelta
    from apps.whatsapp_bot_v4.models import ConversationOwnership

    # Filtrar (mismo código que whatsapp_conversaciones)
    conversaciones = ConversacionWhatsApp.objects.select_related(
        "cliente", "lead", "channel", "responsable"
    )
    conversaciones = _filtrar_conversaciones(conversaciones, request)

    # Prefetch último mensaje eficientemente
    last_mensaje = MensajeWhatsApp.objects.filter(
        conversacion_id=Q
    ).order_by('-fecha_mensaje')[:1]

    data = []
    for conv in conversaciones[:100]:
        # Obtener último mensaje eficientemente
        ultimo_mensaje = conv.mensajes.order_by('-fecha_mensaje').first()

        # Contar mensajes no leídos (entrantes que no están leídos)
        unread_count = MensajeWhatsApp.objects.filter(
            conversacion=conv,
            direccion=MensajeWhatsApp.ENTRANTE
        ).exclude(
            estado__in=['leido', 'entregado']
        ).count()

        # Generar preview del último mensaje
        preview = _get_message_preview(ultimo_mensaje)

        # Obtener información del lead para resumen
        lead = conv.lead

        data.append({
            'id': conv.id,
            'name': conv.cliente.nombre if conv.cliente and conv.cliente.nombre else conv.cliente.telefono if conv.cliente else 'Sin nombre',
            'phone': conv.cliente.telefono if conv.cliente else 'N/A',
            'avatar': None,  # Se genera con iniciales en el front
            'channel': {
                'id': conv.channel.id if conv.channel else None,
                'name': conv.channel.nombre if conv.channel else 'Desconocido',
                'icon': _get_channel_icon(conv.channel.nombre if conv.channel else None),
            },
            'estado_atencion': conv.estado_atencion,
            'estado_cotizacion': conv.estado_cotizacion,
            'preview': preview,
            'unread_count': unread_count,
            'last_activity': conv.ultima_actividad.isoformat() if conv.ultima_actividad else conv.actualizada_en.isoformat(),
            'lead_id': conv.lead.id if conv.lead else None,
            'responsable': {
                'id': conv.responsable.id if conv.responsable else None,
                'nombre': conv.responsable.get_full_name() or conv.responsable.username if conv.responsable else None,
            },
            'service_data': {
                'origin': lead.distrito_origen if lead and lead.distrito_origen else None,
                'destination': lead.distrito_destino if lead and lead.distrito_destino else None,
                'status': _get_cotizacion_status(conv.estado_cotizacion),
                'price': lead.precio_sugerido if lead and lead.precio_sugerido else None,
            } if lead else None,
        })

    return JsonResponse({'conversations': data})


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


@login_required
@whatsapp_required
def conversation_messages(request, conversation_id):
    """Endpoint para traer mensajes de conversación con info completa (polling en vivo)"""
    conversation = get_object_or_404(ConversacionWhatsApp, pk=conversation_id)
    messages = MensajeWhatsApp.objects.filter(
        conversacion=conversation
    ).select_related('autor').order_by('fecha_mensaje')

    messages_list = []
    for msg in messages:
        # Mapear origen a sender type
        sender_type = _map_mensaje_origen_to_sender(msg.origen)

        # Obtener nombre del remitente
        if msg.origen == MensajeWhatsApp.ORIGEN_CLIENTE:
            sender_name = conversation.cliente.nombre if conversation.cliente else 'Cliente'
        elif msg.origen == MensajeWhatsApp.ORIGEN_BOT:
            sender_name = 'TaxiCarga Bot'
        elif msg.origen == MensajeWhatsApp.ORIGEN_ASESOR:
            sender_name = msg.autor.get_full_name() or msg.autor.username if msg.autor else 'Asesor'
        else:
            sender_name = 'Sistema'

        messages_list.append({
            'id': msg.id,
            'sender': sender_type,
            'senderName': sender_name,
            'type': 'text',  # Por ahora solo texto
            'text': msg.contenido,
            'timestamp': msg.fecha_mensaje.isoformat(),
            'status': msg.estado,
            'avatar': None,
        })

    logger.info(f"conversation_messages: {conversation_id} → {len(messages_list)} mensajes")

    return JsonResponse({
        'messages': messages_list,
        'total': len(messages_list),
        'conversation_id': conversation_id,
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
