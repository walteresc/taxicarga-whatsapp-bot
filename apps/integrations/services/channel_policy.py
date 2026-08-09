from django.conf import settings

from ..models import ChannelIntegrationPolicy


FEATURE_FLAGS = {
    "live_sync": "CHATWOOT_LIVE_SYNC_ENABLED",
    "human_takeover": "CHATWOOT_HUMAN_TAKEOVER_ENABLED",
    "return_to_bot": "CHATWOOT_RETURN_TO_BOT_ENABLED",
    "agent_outbound": "CHATWOOT_AGENT_TO_WHATSAPP_ENABLED",
    "commercial_labels": "CHATWOOT_COMMERCIAL_LABELS_ENABLED",
    "meta_outbox": "META_OUTBOX_ENABLED",
}


def integration_policy(channel):
    if channel is None or not getattr(channel, "pk", None):
        return None
    try:
        return channel.integration_policy
    except ChannelIntegrationPolicy.DoesNotExist:
        return None


def is_feature_enabled(channel, feature):
    setting_name = FEATURE_FLAGS.get(feature)
    if setting_name is None:
        raise ValueError(f"Unknown channel integration feature: {feature}")
    policy = integration_policy(channel)
    return bool(
        getattr(settings, setting_name, False)
        and policy
        and policy.enabled
        and getattr(policy, feature)
    )


def integration_enabled(channel):
    policy = integration_policy(channel)
    return bool(policy and policy.enabled)
