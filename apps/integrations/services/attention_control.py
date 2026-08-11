from dataclasses import dataclass

from django.conf import settings

from ..enums import OwnerState
from ..errors import InvalidTransition
from ..models import ConversationMapping
from ..providers.chatwoot.client import ChatwootClient
from ..providers.chatwoot.exceptions import ChatwootError
from .channel_policy import is_feature_enabled
from .state_machine import return_to_bot


ATTRIBUTE_KEY = "taxicarga_attention_control"
ATTRIBUTE_AGENT = "Asesor"
ATTRIBUTE_BOT = "Bot"


@dataclass(frozen=True)
class AttentionControlResult:
    changed: bool
    reflected: bool
    reflection_error: str = ""


def reflect_attention_control(mapping, value, *, client=None):
    client = client or ChatwootClient()
    remote = client.get_conversation(mapping.external_conversation_id)
    attributes = dict(remote.get("custom_attributes") or {}) if isinstance(remote, dict) else {}
    attributes[ATTRIBUTE_KEY] = value
    client.update_conversation_custom_attributes(
        mapping.external_conversation_id,
        attributes,
    )


def _performer_identity(payload):
    performer = payload.get("performer")
    if not isinstance(performer, dict):
        return ""
    performer_id = str(performer.get("id") or "")
    performer_type = str(performer.get("type") or "").lower()
    return performer_id if performer_id and performer_type == "user" else ""


def apply_chatwoot_return_request(*, mapping, payload, account_id, inbox_id, delivery_id, client=None):
    inbox = mapping.contact_inbox.inbox
    performer_id = _performer_identity(payload)
    if (
        not settings.CHATWOOT_RETURN_TO_BOT_ENABLED
        or not mapping.active
        or not inbox.active
        or str(inbox.account.account_id) != str(account_id)
        or str(inbox.inbox_id) != str(inbox_id)
        or inbox.channel_id != mapping.conversation.channel_id
        or not is_feature_enabled(mapping.conversation.channel, "return_to_bot")
    ):
        raise InvalidTransition("Chatwoot return is outside the authorized sandbox scope.")

    control, _audit, changed = return_to_bot(
        mapping.conversation_id,
        actor=None,
        actor_type="chatwoot_agent",
        external_actor_ref=performer_id,
        source="chatwoot_webhook",
        idempotency_key=f"chatwoot-return:{account_id}:{mapping.external_conversation_id}:{delivery_id}",
    )
    reflected = False
    reflection_error = ""
    if changed:
        try:
            # Local transaction already committed. Chatwoot is projection only.
            reflect_attention_control(mapping, ATTRIBUTE_BOT, client=client)
            reflected = True
        except ChatwootError as exc:
            reflection_error = exc.__class__.__name__
    return control, AttentionControlResult(changed, reflected, reflection_error)


def current_attribute_for_owner(owner_state):
    return ATTRIBUTE_AGENT if owner_state == OwnerState.AGENT_ACTIVE else ATTRIBUTE_BOT
