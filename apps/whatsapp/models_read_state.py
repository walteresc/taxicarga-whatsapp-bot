"""
Per-user conversation read state tracking.
Tracks which messages each user has read to compute accurate unread counts.
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class ConversationReadState(models.Model):
    """
    Tracks read state for each user-conversation pair.
    last_read_message_id: the ID of the last message the user has read
    last_read_at: when the user last marked this conversation as read
    """
    conversation = models.ForeignKey(
        "whatsapp.ConversacionWhatsApp",
        on_delete=models.CASCADE,
        related_name="read_states",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="conversation_read_states",
    )
    last_read_message = models.ForeignKey(
        "whatsapp.MensajeWhatsApp",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="read_by_users",
    )
    last_read_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("conversation", "user")
        indexes = [
            models.Index(fields=["user", "conversation"]),
            models.Index(fields=["conversation", "last_read_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} read {self.conversation.id} @ {self.last_read_at}"

    @classmethod
    def mark_read(cls, conversation, user, last_message=None):
        """Mark conversation as read up to the given message"""
        obj, created = cls.objects.update_or_create(
            conversation=conversation,
            user=user,
            defaults={
                "last_read_message": last_message,
                "last_read_at": timezone.now(),
            }
        )
        return obj, created

    @classmethod
    def get_unread_count(cls, conversation, user):
        """Get unread message count for a user in a conversation"""
        from apps.whatsapp.models import MensajeWhatsApp

        read_state = cls.objects.filter(
            conversation=conversation,
            user=user,
        ).first()

        # Count inbound messages after last read
        unread = MensajeWhatsApp.objects.filter(
            conversacion=conversation,
            direccion=MensajeWhatsApp.ENTRANTE,
            sender_type=MensajeWhatsApp.SENDER_CUSTOMER,
        )

        if read_state and read_state.last_read_message:
            unread = unread.filter(fecha_mensaje__gt=read_state.last_read_message.fecha_mensaje)

        return unread.count()
