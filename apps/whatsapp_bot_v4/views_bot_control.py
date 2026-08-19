import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.whatsapp.models import ConversacionWhatsApp
from apps.whatsapp_bot_v4.models import ConversationOwnership, BotGlobalConfig

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def take_control(request, conversation_id):
    """Asesor toma control de la conversación"""
    try:
        conversation = ConversacionWhatsApp.objects.get(id=conversation_id)
    except ConversacionWhatsApp.DoesNotExist:
        return JsonResponse({'error': 'Conversation not found'}, status=404)

    ownership, _ = ConversationOwnership.objects.get_or_create(conversation=conversation)
    ownership.owner_type = ConversationOwnership.OWNER_ADVISOR
    ownership.advisor_id = request.user
    ownership.last_human_message_at = timezone.now()
    ownership.save()

    logger.info(f"Advisor {request.user.id} took control of conversation {conversation_id}")
    return JsonResponse({'status': 'advisor'})


@login_required
@require_http_methods(["POST"])
def return_to_bot(request, conversation_id):
    """Devolver control al bot"""
    try:
        conversation = ConversacionWhatsApp.objects.get(id=conversation_id)
    except ConversacionWhatsApp.DoesNotExist:
        return JsonResponse({'error': 'Conversation not found'}, status=404)

    ownership, _ = ConversationOwnership.objects.get_or_create(conversation=conversation)
    ownership.owner_type = ConversationOwnership.OWNER_BOT
    ownership.advisor_id = None
    ownership.last_human_message_at = None
    ownership.save()

    logger.info(f"Control returned to bot for conversation {conversation_id}")
    return JsonResponse({'status': 'bot'})


@login_required
@require_http_methods(["POST"])
def pause_global(request):
    """Pausar bot en TODAS las conversaciones"""
    config = BotGlobalConfig.objects.first()
    if not config:
        config = BotGlobalConfig.objects.create()

    config.is_paused = True
    config.paused_at = timezone.now()
    config.save()

    logger.warning(f"Bot globally paused by {request.user.id}")
    return JsonResponse({'status': 'paused'})


@login_required
@require_http_methods(["POST"])
def activate_global(request):
    """Activar bot en TODAS las conversaciones"""
    config = BotGlobalConfig.objects.first()
    if not config:
        config = BotGlobalConfig.objects.create()

    config.is_paused = False
    config.paused_at = None
    config.save()

    logger.warning(f"Bot globally activated by {request.user.id}")
    return JsonResponse({'status': 'active'})


@login_required
def get_bot_status(request):
    """GET: estado global y de conversación específica (AJAX)"""
    global_config = BotGlobalConfig.objects.first()
    if not global_config:
        global_config = BotGlobalConfig.objects.create()

    data = {
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
            else:
                data['conversation_owner_type'] = 'bot'
                data['advisor_id'] = None
        except ConversacionWhatsApp.DoesNotExist:
            pass

    return JsonResponse(data)


@login_required
def bot_control_panel(request):
    """Panel de control del bot (HTML)"""
    global_config = BotGlobalConfig.objects.first()
    if not global_config:
        global_config = BotGlobalConfig.objects.create()

    context = {
        'global_config': global_config,
    }
    return render(request, 'whatsapp_bot_v4/bot_control_panel.html', context)
