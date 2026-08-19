import logging
from apps.whatsapp_bot_v4.models import BotGlobalConfig, ConversationOwnership

logger = logging.getLogger(__name__)


def can_bot_respond(conversation_id):
    """PUNTO 1+2: Validar si bot puede responder.

    Cuatro puntos de validación:
    1. Global pause check
    2. Ownership check (bot vs advisor)
    3. (Pre-LLM check)
    4. (Pre-send check)
    """
    # PUNTO 1: Control global
    global_config = BotGlobalConfig.objects.first()
    if not global_config:
        global_config = BotGlobalConfig.objects.create()

    if global_config.is_paused:
        logger.warning(f"Bot globally paused")
        return False

    # PUNTO 2: Control de conversación específica
    try:
        ownership = ConversationOwnership.objects.get(conversation_id=conversation_id)
    except ConversationOwnership.DoesNotExist:
        # Si no existe, crear con default bot
        ownership = ConversationOwnership.objects.create(conversation_id=conversation_id)

    if not ownership.is_bot_allowed():
        logger.warning(f"Bot not allowed for conversation {conversation_id}, owner_type={ownership.owner_type}")
        return False

    return True


def get_or_create_global_config():
    """Obtener o crear configuración global"""
    config, created = BotGlobalConfig.objects.get_or_create(pk=1)
    return config
