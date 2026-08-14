class ChatwootV4Adapter:
    """Small V4 facade over existing durable Chatwoot integration."""

    @staticmethod
    def get_owner(conversation):
        from apps.integrations.enums import OwnerState
        from apps.integrations.models import ConversationControl

        control, _ = ConversationControl.objects.get_or_create(conversation=conversation)
        return control.owner_state or OwnerState.BOT_ACTIVE

    def is_bot_allowed(self, conversation) -> bool:
        from apps.integrations.enums import OwnerState

        return self.get_owner(conversation) == OwnerState.BOT_ACTIVE

    @staticmethod
    def project_customer_message(message):
        from apps.integrations.services.live_sync import project_new_incoming
        from apps.whatsapp.models import MensajeWhatsApp

        if message.direccion != MensajeWhatsApp.ENTRANTE or message.origen != MensajeWhatsApp.ORIGEN_CLIENTE:
            return None
        return project_new_incoming(message)

    @staticmethod
    def project_bot_message(message):
        from apps.integrations.services.live_sync import queue_outgoing_message_projection
        from apps.whatsapp.models import MensajeWhatsApp

        if message.direccion != MensajeWhatsApp.SALIENTE or message.origen != MensajeWhatsApp.ORIGEN_BOT:
            return None
        return queue_outgoing_message_projection(message)

    @staticmethod
    def project_private_note(_message):
        return None

    @staticmethod
    def project_commercial_status(conversation):
        from apps.integrations.services.commercial_labels import queue_commercial_label_projection

        return queue_commercial_label_projection(conversation.id)

    @staticmethod
    def handoff_to_agent(conversation, *, reason, idempotency_key):
        from apps.integrations.services.state_machine import request_agent

        return request_agent(
            conversation.id,
            reason=reason,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def return_to_bot(conversation, *, actor, idempotency_key, instruction=""):
        from apps.integrations.services.state_machine import return_to_bot

        return return_to_bot(
            conversation.id,
            actor=actor,
            instruction=instruction,
            idempotency_key=idempotency_key,
        )
