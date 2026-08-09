from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Lead, LeadUbicacion


def _queue_after_commit(lead_id):
    def queue():
        from apps.integrations.services.conversation_data import queue_conversation_data_projection
        from apps.whatsapp.models import ConversacionWhatsApp

        conversation_ids = ConversacionWhatsApp.objects.filter(
            lead_id=lead_id
        ).exclude(estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA).values_list("id", flat=True)
        for conversation_id in conversation_ids:
            queue_conversation_data_projection(conversation_id)

    transaction.on_commit(queue)


@receiver(post_save, sender=Lead)
def project_lead_change(sender, instance, **kwargs):
    _queue_after_commit(instance.id)


@receiver([post_save, post_delete], sender=LeadUbicacion)
def project_location_change(sender, instance, **kwargs):
    _queue_after_commit(instance.lead_id)
