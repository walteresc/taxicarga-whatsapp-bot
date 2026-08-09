from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.integrations.enums import Provider, SyncStatus
from apps.integrations.models import (
    ChannelInboxMapping,
    ChatwootContactMapping,
    ContactInboxMapping,
    ConversationMapping,
    ExternalMessageMapping,
)
from apps.integrations.providers.chatwoot.client import ChatwootClient
from apps.integrations.providers.chatwoot.exceptions import (
    ChatwootConfigurationError,
    ChatwootNotFoundError,
)
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
from apps.integrations.services.channel_policy import integration_enabled, is_feature_enabled


@dataclass(frozen=True)
class ProjectionResult:
    django_contact_id: int
    chatwoot_contact_id: str
    source_id: str
    contact_created: bool
    django_conversation_id: int
    chatwoot_conversation_id: str
    conversation_created: bool
    total: int
    incoming: int
    outgoing: int
    messages_created: int
    messages_reused: int
    messages_failed: int
    failure: str = ""
    dry_run: bool = False


def contact_identifier(cliente_id):
    return f"taxicarga-contact:{cliente_id}"


def conversation_identifier(conversation_id):
    return f"taxicarga-conversation:{conversation_id}"


def message_identifier(message_id):
    return f"taxicarga-message:{message_id}"


def _contact_payload(payload):
    items = payload.get("payload") if isinstance(payload, dict) else None
    if isinstance(items, list) and items:
        contact = dict(items[0])
        contact.setdefault("id", payload.get("id"))
        return contact
    if isinstance(items, dict):
        contact = dict(items.get("contact", items))
        contact.setdefault("id", payload.get("id"))
        contact_inbox = items.get("contact_inbox")
        if contact_inbox and not contact.get("contact_inboxes"):
            contact["contact_inboxes"] = [contact_inbox]
        return contact
    return payload


def _source_for(contact, inbox_id):
    for item in contact.get("contact_inboxes", []):
        if str(item.get("inbox", {}).get("id")) == str(inbox_id):
            return str(item.get("source_id") or "")
    return ""


def _visible_messages(conversation, message_ids=None):
    queryset = conversation.mensajes.filter(tipo="texto")
    if message_ids is not None:
        queryset = queryset.filter(id__in=message_ids)
    return list(
        queryset
        .exclude(origen=MensajeWhatsApp.ORIGEN_SISTEMA)
        .exclude(contenido="")
        .order_by("fecha_mensaje", "id")
    )


def sync_chatwoot_conversation(
    conversation_id, *, dry_run=False, client=None, message_ids=None, live=False
):
    conversation = ConversacionWhatsApp.objects.select_related("cliente", "channel").get(pk=conversation_id)
    messages = _visible_messages(conversation, message_ids)
    incoming = sum(item.direccion == MensajeWhatsApp.ENTRANTE for item in messages)
    outgoing = len(messages) - incoming
    if dry_run:
        return ProjectionResult(
            conversation.cliente_id, "", "", False, conversation.id, "", False,
            len(messages), incoming, outgoing, 0, 0, 0, dry_run=True,
        )
    if live and not is_feature_enabled(conversation.channel, "live_sync"):
        raise ChatwootConfigurationError("Chatwoot live sync is disabled for conversation channel.")
    if not live and (not settings.CHATWOOT_SYNC_ENABLED or not integration_enabled(conversation.channel)):
        raise ChatwootConfigurationError("Chatwoot conversation sync is disabled.")
    if not conversation.channel_id:
        raise ChatwootConfigurationError("Conversation has no channel for Chatwoot inbox mapping.")
    api = client or ChatwootClient()
    now = timezone.now()

    with transaction.atomic():
        conversation = (
            ConversacionWhatsApp.objects.select_for_update(of=("self",))
            .select_related("cliente", "channel")
            .get(pk=conversation_id)
        )
        Cliente.objects.select_for_update().get(pk=conversation.cliente_id)
        existing_conversation_map = (
            ConversationMapping.objects.select_related(
                "contact_inbox__inbox__account"
            )
            .filter(conversation=conversation, active=True)
            .first()
        )
        inbox = (
            ChannelInboxMapping.objects.select_related("account")
            .filter(channel=conversation.channel, active=True, account__active=True)
            .first()
        )
        if not inbox or not inbox.inbox_id or not inbox.account.account_id:
            raise ChatwootConfigurationError(
                "Conversation channel has no active Chatwoot inbox mapping."
            )
        account = inbox.account
        target_account_id = str(account.account_id)
        target_inbox_id = str(inbox.inbox_id)
        api.get_inbox(target_inbox_id)

        identifier = contact_identifier(conversation.cliente_id)
        contact_map = ChatwootContactMapping.objects.filter(
            cliente=conversation.cliente, account=account, active=True
        ).first()
        contact_created = False
        if contact_map:
            try:
                contact = _contact_payload(api.get_contact(contact_map.contact_id))
            except ChatwootNotFoundError:
                contact_map.sync_status = SyncStatus.STALE
                contact_map.last_error = "Remote contact mapping not found."
                contact_map.save(update_fields=["sync_status", "last_error"])
                raise
        else:
            matches = [item for item in api.search_contacts(identifier) if item.get("identifier") == identifier]
            if matches:
                contact = matches[0]
            else:
                contact = _contact_payload(api.create_contact(
                    inbox_id=target_inbox_id,
                    identifier=identifier,
                    name=conversation.cliente.nombre or f"TEST TaxiCarga {conversation.cliente_id}",
                    email=conversation.cliente.correo,
                ))
                contact_created = True
            contact_map = ChatwootContactMapping.objects.create(
                cliente=conversation.cliente,
                account=account,
                contact_id=str(contact["id"]),
                active=True,
                sync_status=SyncStatus.SYNCED,
                last_synced_at=now,
            )

        source_id = _source_for(contact, target_inbox_id)
        contact_inbox = ContactInboxMapping.objects.filter(contact=contact_map, inbox=inbox).first()
        if contact_inbox and contact_inbox.source_id:
            source_id = str(contact_inbox.source_id)
        if not source_id:
            source_id = f"taxicarga-source:{conversation.cliente_id}:{target_inbox_id}"
            api.create_contact_inbox(
                contact_id=contact_map.contact_id,
                inbox_id=target_inbox_id,
                source_id=source_id,
            )
        contact_inbox, _ = ContactInboxMapping.objects.update_or_create(
            contact=contact_map,
            inbox=inbox,
            defaults={"source_id": source_id, "sync_status": SyncStatus.SYNCED, "last_synced_at": now},
        )

        conv_key = conversation_identifier(conversation.id)
        conversation_map = existing_conversation_map
        conversation_created = False
        if conversation_map:
            try:
                api.get_conversation(conversation_map.external_conversation_id)
            except ChatwootNotFoundError:
                conversation_map.sync_status = SyncStatus.STALE
                conversation_map.last_error = "Remote conversation mapping not found."
                conversation_map.save(update_fields=["sync_status", "last_error"])
                raise
            remote_conversation_id = str(conversation_map.external_conversation_id)
        else:
            remote = next((
                item for item in api.list_conversations(inbox_id=target_inbox_id)
                if item.get("additional_attributes", {}).get("taxicarga_conversation_id") == conv_key
            ), None)
            if remote is None:
                remote = api.create_conversation(
                    source_id=source_id,
                    inbox_id=target_inbox_id,
                    contact_id=contact_map.contact_id,
                    canonical_id=conv_key,
                )
                conversation_created = True
            remote_conversation_id = str(remote["id"])
            conversation_map = ConversationMapping.objects.create(
                conversation=conversation,
                contact_inbox=contact_inbox,
                external_conversation_id=remote_conversation_id,
                active=True,
                sync_status=SyncStatus.SYNCED,
                last_synced_at=now,
            )

        remote_messages = api.list_messages(remote_conversation_id)
        remote_by_key = {
            item.get("content_attributes", {}).get("taxicarga_message_id"): item
            for item in remote_messages
            if item.get("content_attributes", {}).get("taxicarga_origin") == "django_projection"
        }
        created = reused = failed = 0
        failure = ""
        for message in messages:
            mapping = ExternalMessageMapping.objects.filter(
                provider=Provider.CHATWOOT,
                account_scope=target_account_id,
                whatsapp_message=message,
            ).first()
            if mapping and mapping.external_id:
                reused += 1
                continue
            key = message_identifier(message.id)
            try:
                remote_message = remote_by_key.get(key)
                was_created = remote_message is None
                if was_created:
                    remote_message = api.create_message(
                        conversation_id=remote_conversation_id,
                        content=message.contenido,
                        message_type="incoming" if message.direccion == MensajeWhatsApp.ENTRANTE else "outgoing",
                        canonical_id=key,
                    )
                ExternalMessageMapping.objects.update_or_create(
                    provider=Provider.CHATWOOT,
                    account_scope=target_account_id,
                    whatsapp_message=message,
                    defaults={
                        "external_id": str(remote_message["id"]),
                        "sync_status": SyncStatus.SYNCED,
                        "last_synced_at": now,
                        "last_error": "",
                    },
                )
                created += int(was_created)
                reused += int(not was_created)
            except Exception as exc:
                failed = 1
                failure = str(exc)
                break

    from .conversation_data import queue_conversation_data_projection
    queue_conversation_data_projection(conversation.id)
    return ProjectionResult(
        conversation.cliente_id, str(contact_map.contact_id), source_id, contact_created,
        conversation.id, remote_conversation_id, conversation_created,
        len(messages), incoming, outgoing, created, reused, failed, failure,
    )
