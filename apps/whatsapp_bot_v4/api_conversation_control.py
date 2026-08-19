"""API endpoints para control de conversación agnóstico a CRM."""

import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import datetime

from apps.whatsapp.models import ConversacionWhatsApp
from .models import ConversationOwnership, BotGlobalConfig

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def transfer_to_advisor(request):
    """CRM endpoint: Asesor toma control de conversación.

    POST /api/v4/conversation-control/transfer-to-advisor/
    {
        "conversation_id": 123,
        "advisor_id": 456,
        "mode": "manual"  # or "automatic"
    }
    """
    conversation_id = request.data.get('conversation_id')
    advisor_id = request.data.get('advisor_id')

    # Security: Advisor can only transfer control to themselves
    if int(advisor_id) != request.user.id:
        logger.warning(
            "conversation_control unauthorized_transfer attempt_by=%s for_advisor=%s",
            request.user.id, advisor_id,
        )
        return Response(
            {"error": "Can only transfer control to yourself"},
            status=status.HTTP_403_FORBIDDEN
        )
    control_mode = request.data.get('mode', 'manual')

    if not conversation_id:
        return Response(
            {"error": "conversation_id required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        conversation = ConversacionWhatsApp.objects.get(pk=conversation_id)
    except ConversacionWhatsApp.DoesNotExist:
        return Response(
            {"error": f"Conversation {conversation_id} not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    ownership, created = ConversationOwnership.objects.update_or_create(
        conversation=conversation,
        defaults={
            "owner_type": ConversationOwnership.OWNER_ADVISOR,
            "advisor_id_id": advisor_id,
            "control_mode": control_mode,
            "last_human_message_at": timezone.now(),
        }
    )

    logger.info(
        "conversation_control transfer_to_advisor conversation_id=%s advisor_id=%s mode=%s",
        conversation_id, advisor_id, control_mode,
    )

    return Response({
        "status": "advisor_now_in_control",
        "conversation_id": conversation_id,
        "advisor_id": advisor_id,
        "control_mode": control_mode,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def return_to_bot(request):
    """CRM endpoint: Bot recupera control.

    POST /api/v4/conversation-control/return-to-bot/
    {
        "conversation_id": 123
    }
    """
    conversation_id = request.data.get('conversation_id')

    if not conversation_id:
        return Response(
            {"error": "conversation_id required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        conversation = ConversacionWhatsApp.objects.get(pk=conversation_id)
    except ConversacionWhatsApp.DoesNotExist:
        return Response(
            {"error": f"Conversation {conversation_id} not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    ownership, _ = ConversationOwnership.objects.update_or_create(
        conversation=conversation,
        defaults={
            "owner_type": ConversationOwnership.OWNER_BOT,
            "advisor_id": None,
        }
    )

    logger.info(
        "conversation_control return_to_bot conversation_id=%s",
        conversation_id,
    )

    return Response({
        "status": "bot_now_in_control",
        "conversation_id": conversation_id,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def advisor_detected(request):
    """CRM endpoint: Asesor fue detectado escribiendo (automático).

    POST /api/v4/conversation-control/advisor-detected/
    {
        "conversation_id": 123,
        "advisor_id": 456
    }
    """
    conversation_id = request.data.get('conversation_id')
    advisor_id = request.data.get('advisor_id')

    # Security: Only an advisor can report themselves as detected
    if int(advisor_id) != request.user.id:
        logger.warning(
            "conversation_control unauthorized_detection attempt_by=%s for_advisor=%s",
            request.user.id, advisor_id,
        )
        return Response(
            {"error": "Can only report yourself as detected"},
            status=status.HTTP_403_FORBIDDEN
        )

    if not conversation_id or not advisor_id:
        return Response(
            {"error": "conversation_id and advisor_id required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        conversation = ConversacionWhatsApp.objects.get(pk=conversation_id)
    except ConversacionWhatsApp.DoesNotExist:
        return Response(
            {"error": f"Conversation {conversation_id} not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    ownership, _ = ConversationOwnership.objects.get_or_create(conversation=conversation)

    if ownership.control_mode == ConversationOwnership.MODE_AUTOMATIC:
        ownership.owner_type = ConversationOwnership.OWNER_ADVISOR
        ownership.advisor_id_id = advisor_id
        ownership.last_human_message_at = timezone.now()
        ownership.save(update_fields=['owner_type', 'advisor_id', 'last_human_message_at'])
        auto_control_taken = True
    else:
        auto_control_taken = False

    logger.info(
        "conversation_control advisor_detected conversation_id=%s advisor_id=%s auto_taken=%s",
        conversation_id, advisor_id, auto_control_taken,
    )

    return Response({
        "status": "advisor_detected",
        "conversation_id": conversation_id,
        "auto_control_taken": auto_control_taken,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def transaction_completed(request):
    """CRM endpoint: Transacción completada → cierra conversación.

    POST /api/v4/conversation-control/transaction-completed/
    {
        "conversation_id": 123
    }
    """
    conversation_id = request.data.get('conversation_id')

    if not conversation_id:
        return Response(
            {"error": "conversation_id required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        conversation = ConversacionWhatsApp.objects.get(pk=conversation_id)
    except ConversacionWhatsApp.DoesNotExist:
        return Response(
            {"error": f"Conversation {conversation_id} not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    conversation.estado_atencion = ConversacionWhatsApp.ATENCION_CERRADA
    conversation.cerrada_en = timezone.now()
    conversation.save(update_fields=['estado_atencion', 'cerrada_en'])

    logger.info(
        "conversation_control transaction_completed conversation_id=%s",
        conversation_id,
    )

    return Response({
        "status": "conversation_closed",
        "conversation_id": conversation_id,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def transaction_cancelled(request):
    """CRM endpoint: Transacción cancelada → devuelve al bot.

    POST /api/v4/conversation-control/transaction-cancelled/
    {
        "conversation_id": 123
    }
    """
    conversation_id = request.data.get('conversation_id')

    if not conversation_id:
        return Response(
            {"error": "conversation_id required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        conversation = ConversacionWhatsApp.objects.get(pk=conversation_id)
    except ConversacionWhatsApp.DoesNotExist:
        return Response(
            {"error": f"Conversation {conversation_id} not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    ownership, _ = ConversationOwnership.objects.update_or_create(
        conversation=conversation,
        defaults={
            "owner_type": ConversationOwnership.OWNER_BOT,
            "advisor_id": None,
        }
    )

    # Reabrir conversación si estaba cerrada
    if conversation.estado_atencion == ConversacionWhatsApp.ATENCION_CERRADA:
        conversation.estado_atencion = ConversacionWhatsApp.ATENCION_BOT
        conversation.cerrada_en = None
        conversation.save(update_fields=['estado_atencion', 'cerrada_en'])

    logger.info(
        "conversation_control transaction_cancelled conversation_id=%s",
        conversation_id,
    )

    return Response({
        "status": "bot_reactivated",
        "conversation_id": conversation_id,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def pause_global(request):
    """Control global: Pausar bot en TODAS las conversaciones.

    POST /api/v4/conversation-control/pause-global/
    """
    config = BotGlobalConfig.objects.first()
    if not config:
        config = BotGlobalConfig.objects.create()

    config.is_paused = True
    config.paused_at = timezone.now()
    config.save()

    logger.warning(
        "bot_control global_pause user_id=%s",
        request.user.id,
    )

    return Response({
        "status": "paused",
        "message": "Bot paused globally for all conversations",
        "is_paused": True,
        "paused_at": config.paused_at.isoformat(),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def activate_global(request):
    """Control global: Activar bot en TODAS las conversaciones.

    POST /api/v4/conversation-control/activate-global/
    """
    config = BotGlobalConfig.objects.first()
    if not config:
        config = BotGlobalConfig.objects.create()

    config.is_paused = False
    config.paused_at = None
    config.save()

    # Resetear todos los ownership a BOT cuando se activa (permitir que bot responda)
    ConversationOwnership.objects.all().update(
        owner_type=ConversationOwnership.OWNER_BOT,
        control_mode=ConversationOwnership.MODE_AUTOMATIC,
        advisor_id=None
    )

    logger.warning(
        "bot_control global_activate user_id=%s",
        request.user.id,
    )

    # Procesar conversaciones pendientes (en background)
    from apps.whatsapp_bot_v4.services.ycloud_webhook_service import process_pending_conversations
    try:
        process_pending_conversations()
    except Exception as e:
        logger.error(f"Error processing pending conversations on activate: {e}", exc_info=True)

    return Response({
        "status": "active",
        "message": "Bot activated globally for all conversations",
        "is_paused": False,
        "paused_at": None,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_bot_status(request):
    """GET: Estado global del bot y estado de conversación específica.

    GET /api/v4/conversation-control/bot-status/?conversation_id=123
    """
    global_config = BotGlobalConfig.objects.first()
    if not global_config:
        global_config = BotGlobalConfig.objects.create()

    data = {
        'is_paused': global_config.is_paused,
        'global_paused': global_config.is_paused,
        'paused_at': global_config.paused_at.isoformat() if global_config.paused_at else None,
    }

    # Si hay conversation_id en query string, agregar estado específico
    conversation_id = request.GET.get('conversation_id')
    if conversation_id:
        try:
            conversation = ConversacionWhatsApp.objects.get(id=conversation_id)
            ownership = ConversationOwnership.objects.filter(conversation=conversation).first()
            if ownership:
                data['conversation_owner_type'] = ownership.owner_type
                data['advisor_id'] = ownership.advisor_id_id if ownership.advisor_id else None
                data['advisor_name'] = ownership.advisor_id.get_full_name() if ownership.advisor_id else None
            else:
                data['conversation_owner_type'] = 'bot'
                data['advisor_id'] = None
                data['advisor_name'] = None
        except ConversacionWhatsApp.DoesNotExist:
            pass

    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_active_conversations(request):
    """GET: Lista de conversaciones activas con estado de control.

    GET /api/v4/conversation-control/conversations/
    """
    from apps.whatsapp.models import ConversacionWhatsApp

    conversations = ConversacionWhatsApp.objects.select_related(
        'cliente'
    ).exclude(estado_atencion='cerrada').order_by('-actualizada_en')[:50]

    data = []
    for conv in conversations:
        # Obtener ownership
        try:
            ownership = ConversationOwnership.objects.get(conversation=conv)
        except ConversationOwnership.DoesNotExist:
            ownership = None

        data.append({
            'id': conv.id,
            'cliente_phone': conv.cliente.telefono if conv.cliente else 'Desconocido',
            'cliente_name': conv.cliente.nombre if conv.cliente else 'Sin nombre',
            'owner_type': ownership.owner_type if ownership else 'bot',
            'advisor_id': ownership.advisor_id_id if ownership and ownership.advisor_id else None,
            'advisor_name': ownership.advisor_id.get_full_name() if ownership and ownership.advisor_id else None,
        })

    return Response(data)
