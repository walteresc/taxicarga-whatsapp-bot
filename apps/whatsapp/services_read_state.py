"""
Read state management service.
"""
from django.utils import timezone
from apps.whatsapp.models_read_state import ConversationReadState
from apps.whatsapp.models import MensajeWhatsApp
import logging

logger = logging.getLogger(__name__)


def mark_conversation_as_read(conversation, user):
    """
    Mark all messages in a conversation as read for a given user.
    Called when user opens the conversation in CRM.
    """
    # Get the latest message in the conversation
    last_message = (
        MensajeWhatsApp.objects.filter(conversacion=conversation)
        .order_by("-fecha_mensaje")
        .first()
    )

    if not last_message:
        logger.warning(f"[ReadState] No messages in conversation {conversation.id}")
        return None

    read_state, created = ConversationReadState.mark_read(
        conversation=conversation,
        user=user,
        last_message=last_message,
    )

    logger.info(
        f"[ReadState] Marked conversation {conversation.id} as read by {user.username} "
        f"(up to message {last_message.id})"
    )

    return read_state


def get_unread_count(conversation, user):
    """
    Get the number of unread inbound messages for a user in a conversation.
    """
    return ConversationReadState.get_unread_count(conversation, user)


def get_unread_conversations(user):
    """
    Get dict of conversation_id -> unread_count for all conversations with unread messages.
    """
    from apps.whatsapp.models import ConversacionWhatsApp

    conversations = ConversacionWhatsApp.objects.all()
    unread_map = {}

    for conv in conversations:
        unread_count = get_unread_count(conv, user)
        if unread_count > 0:
            unread_map[conv.id] = unread_count

    return unread_map
