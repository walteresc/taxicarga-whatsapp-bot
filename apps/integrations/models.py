import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .enums import (
    AuthorType,
    CheckpointStatus,
    ContentType,
    Direction,
    GenerationStatus,
    InboxStatus,
    OutboxStatus,
    OwnerState,
    Provider,
    ResumeMode,
    SyncStatus,
    Visibility,
)


class ConversationControl(models.Model):
    conversation = models.OneToOneField(
        "whatsapp.ConversacionWhatsApp", on_delete=models.CASCADE, related_name="integration_control"
    )
    owner_state = models.CharField(max_length=24, choices=OwnerState.choices, default=OwnerState.BOT_ACTIVE)
    control_version = models.PositiveBigIntegerField(default=0)
    active_advisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="integration_controls",
    )
    requested_at = models.DateTimeField(null=True, blank=True)
    taken_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    last_reason = models.CharField(max_length=120, blank=True)
    last_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="integration_control_actions",
    )
    last_actor_type = models.CharField(max_length=30, blank=True)
    last_correlation_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["owner_state", "updated_at"], name="int_ctrl_state_idx")]


class ConversationTransitionAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        "whatsapp.ConversacionWhatsApp", on_delete=models.CASCADE, related_name="integration_audits"
    )
    from_state = models.CharField(max_length=24, choices=OwnerState.choices)
    to_state = models.CharField(max_length=24, choices=OwnerState.choices)
    action = models.CharField(max_length=50)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor_type = models.CharField(max_length=30, default="system")
    external_actor_ref = models.CharField(max_length=160, blank=True)
    source = models.CharField(max_length=50, blank=True)
    version_before = models.PositiveBigIntegerField()
    version_after = models.PositiveBigIntegerField()
    reason = models.CharField(max_length=200, blank=True)
    idempotency_key = models.CharField(max_length=200)
    correlation_id = models.UUIDField(default=uuid.uuid4)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "action", "idempotency_key"], name="int_audit_action_idem_uniq"
            )
        ]
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="int_audit_conv_idx"),
            models.Index(fields=["correlation_id"], name="int_audit_corr_idx"),
        ]


class IntegrationMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        "whatsapp.ConversacionWhatsApp", on_delete=models.CASCADE, related_name="integration_messages"
    )
    provider = models.CharField(max_length=30, choices=Provider.choices)
    external_scope = models.CharField(max_length=160, default="internal")
    channel = models.ForeignKey("whatsapp.WhatsAppChannel", null=True, blank=True, on_delete=models.PROTECT)
    external_message_id = models.CharField(max_length=255, null=True, blank=True)
    direction = models.CharField(max_length=12, choices=Direction.choices)
    author_type = models.CharField(max_length=20, choices=AuthorType.choices)
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PRIVATE)
    content_type = models.CharField(max_length=30, choices=ContentType.choices, default=ContentType.TEXT)
    text = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=255)
    correlation_id = models.UUIDField(default=uuid.uuid4)
    external_timestamp = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_scope", "external_message_id"],
                condition=models.Q(external_message_id__isnull=False) & ~models.Q(external_message_id=""),
                name="int_msg_scope_ext_uniq",
            ),
            models.UniqueConstraint(fields=["provider", "external_scope", "idempotency_key"], name="int_msg_scope_idem_uniq"),
        ]
        indexes = [
            models.Index(fields=["conversation", "received_at", "id"], name="int_msg_conv_order_idx"),
            models.Index(fields=["correlation_id"], name="int_msg_corr_idx"),
        ]


class BotGeneration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        "whatsapp.ConversacionWhatsApp", on_delete=models.CASCADE, related_name="bot_generations"
    )
    input_message = models.ForeignKey(
        IntegrationMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name="generations"
    )
    control_version_started = models.PositiveBigIntegerField()
    expected_owner_state = models.CharField(max_length=24, choices=OwnerState.choices, default=OwnerState.BOT_ACTIVE)
    status = models.CharField(max_length=15, choices=GenerationStatus.choices, default=GenerationStatus.PENDING)
    request_key = models.CharField(max_length=255)
    result_text = models.TextField(blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=120, blank=True)
    error_summary = models.CharField(max_length=255, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["conversation", "request_key"], name="int_gen_request_uniq")
        ]
        indexes = [
            models.Index(fields=["conversation", "status", "started_at"], name="int_gen_active_idx"),
            models.Index(fields=["correlation_id"], name="int_gen_corr_idx"),
        ]


class IntegrationInboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=30, choices=Provider.choices)
    external_scope = models.CharField(max_length=160, default="internal")
    external_event_id = models.CharField(max_length=255, null=True, blank=True)
    event_type = models.CharField(max_length=80)
    idempotency_key = models.CharField(max_length=255)
    payload_hash = models.CharField(max_length=64)
    safe_payload = models.JSONField(default=dict, blank=True)
    account_ref = models.CharField(max_length=120, blank=True)
    inbox_ref = models.CharField(max_length=120, blank=True)
    channel = models.ForeignKey("whatsapp.WhatsAppChannel", null=True, blank=True, on_delete=models.SET_NULL)
    conversation = models.ForeignKey("whatsapp.ConversacionWhatsApp", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=InboxStatus.choices, default=InboxStatus.RECEIVED)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=8)
    received_at = models.DateTimeField(default=timezone.now)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=120, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_summary = models.CharField(max_length=255, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "external_scope", "idempotency_key"], name="int_inbox_scope_idem_uniq"),
            models.UniqueConstraint(
                fields=["provider", "external_scope", "external_event_id"],
                condition=models.Q(external_event_id__isnull=False) & ~models.Q(external_event_id=""),
                name="int_inbox_scope_ext_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "next_retry_at"], name="int_inbox_retry_idx"),
            models.Index(fields=["conversation", "status", "received_at"], name="int_inbox_conv_idx"),
            models.Index(fields=["correlation_id"], name="int_inbox_corr_idx"),
            models.Index(fields=["locked_at"], name="int_inbox_lock_idx"),
        ]


class IntegrationOutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    destination = models.CharField(max_length=30, choices=Provider.choices)
    destination_scope = models.CharField(max_length=160, default="internal")
    event_type = models.CharField(max_length=80)
    logical_message = models.ForeignKey(
        IntegrationMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name="outbox_events"
    )
    idempotency_key = models.CharField(max_length=255)
    conversation = models.ForeignKey("whatsapp.ConversacionWhatsApp", on_delete=models.CASCADE)
    safe_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=OutboxStatus.choices, default=OutboxStatus.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=8)
    available_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=120, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    external_id = models.CharField(max_length=255, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_summary = models.CharField(max_length=255, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["destination", "destination_scope", "idempotency_key"], name="int_outbox_scope_idem_uniq"),
            models.UniqueConstraint(
                fields=["destination", "destination_scope", "logical_message", "event_type"],
                condition=models.Q(logical_message__isnull=False),
                name="int_outbox_logical_dest_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "available_at"], name="int_outbox_available_idx"),
            models.Index(fields=["conversation", "status", "created_at"], name="int_outbox_conv_idx"),
            models.Index(fields=["correlation_id"], name="int_outbox_corr_idx"),
            models.Index(fields=["locked_at"], name="int_outbox_lock_idx"),
        ]


class ChatwootAccountMapping(models.Model):
    environment = models.CharField(max_length=40)
    account_id = models.CharField(max_length=80, null=True, blank=True)
    active = models.BooleanField(default=False)
    sync_status = models.CharField(max_length=15, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    last_error = models.CharField(max_length=255, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["environment", "account_id"], condition=models.Q(account_id__isnull=False) & ~models.Q(account_id=""), name="int_cw_account_uniq")]

    def clean(self):
        if self.active and not self.account_id:
            raise ValidationError("Active account mapping requires account_id.")


class ChannelInboxMapping(models.Model):
    channel = models.ForeignKey("whatsapp.WhatsAppChannel", on_delete=models.CASCADE, related_name="chatwoot_mappings")
    account = models.ForeignKey(ChatwootAccountMapping, on_delete=models.CASCADE, related_name="inboxes")
    inbox_id = models.CharField(max_length=80, null=True, blank=True)
    inbox_identifier = models.CharField(max_length=160, blank=True)
    active = models.BooleanField(default=False)
    sync_status = models.CharField(max_length=15, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    last_error = models.CharField(max_length=255, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "inbox_id"], condition=models.Q(inbox_id__isnull=False) & ~models.Q(inbox_id=""), name="int_cw_inbox_uniq"),
            models.UniqueConstraint(fields=["channel"], condition=models.Q(active=True), name="int_channel_active_inbox_uniq"),
        ]

    def clean(self):
        if self.active and (not self.inbox_id or not self.inbox_identifier or not self.account.active):
            raise ValidationError("Active inbox mapping requires active account and external identifiers.")


class ChatwootContactMapping(models.Model):
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.CASCADE, related_name="chatwoot_mappings")
    account = models.ForeignKey(ChatwootAccountMapping, on_delete=models.CASCADE)
    contact_id = models.CharField(max_length=80, null=True, blank=True)
    active = models.BooleanField(default=False)
    sync_status = models.CharField(max_length=15, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    last_error = models.CharField(max_length=255, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "contact_id"], condition=models.Q(contact_id__isnull=False) & ~models.Q(contact_id=""), name="int_cw_contact_uniq"),
            models.UniqueConstraint(fields=["cliente", "account"], condition=models.Q(active=True), name="int_client_active_contact_uniq"),
        ]

    def clean(self):
        if self.active and (not self.contact_id or not self.account.active):
            raise ValidationError("Active contact mapping requires active account and contact_id.")


class ContactInboxMapping(models.Model):
    contact = models.ForeignKey(ChatwootContactMapping, on_delete=models.CASCADE, related_name="inbox_sources")
    inbox = models.ForeignKey(ChannelInboxMapping, on_delete=models.CASCADE, related_name="contact_sources")
    source_id = models.CharField(max_length=160, null=True, blank=True)
    sync_status = models.CharField(max_length=15, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    last_error = models.CharField(max_length=255, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["inbox", "source_id"], condition=models.Q(source_id__isnull=False) & ~models.Q(source_id=""), name="int_cw_source_uniq"),
            models.UniqueConstraint(fields=["contact", "inbox"], name="int_cw_contact_inbox_uniq"),
        ]


class ConversationMapping(models.Model):
    conversation = models.ForeignKey("whatsapp.ConversacionWhatsApp", on_delete=models.CASCADE, related_name="chatwoot_mappings")
    contact_inbox = models.ForeignKey(ContactInboxMapping, on_delete=models.CASCADE)
    external_conversation_id = models.CharField(max_length=80, null=True, blank=True)
    active = models.BooleanField(default=False)
    sync_status = models.CharField(max_length=15, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    last_error = models.CharField(max_length=255, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contact_inbox", "external_conversation_id"],
                condition=models.Q(external_conversation_id__isnull=False) & ~models.Q(external_conversation_id=""),
                name="int_cw_conversation_uniq"
            ),
            models.UniqueConstraint(
                fields=["conversation"], condition=models.Q(active=True), name="int_local_active_conv_map_uniq"
            ),
        ]

    def clean(self):
        expected_channel_id = self.contact_inbox.inbox.channel_id
        if self.conversation.channel_id != expected_channel_id:
            raise ValidationError("Conversation mapping channel is inconsistent.")
        if self.conversation.cliente_id != self.contact_inbox.contact.cliente_id:
            raise ValidationError("Conversation mapping contact is inconsistent.")
        if self.active and (not self.external_conversation_id or not self.contact_inbox.inbox.active):
            raise ValidationError("Active conversation mapping requires active inbox and external ID.")


class ExternalMessageMapping(models.Model):
    logical_message = models.ForeignKey(IntegrationMessage, null=True, blank=True, on_delete=models.SET_NULL)
    whatsapp_message = models.ForeignKey("whatsapp.MensajeWhatsApp", null=True, blank=True, on_delete=models.SET_NULL)
    provider = models.CharField(max_length=30, choices=Provider.choices)
    account_scope = models.CharField(max_length=120, blank=True)
    external_id = models.CharField(max_length=255, null=True, blank=True)
    sync_status = models.CharField(max_length=15, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    last_error = models.CharField(max_length=255, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "account_scope", "external_id"], condition=models.Q(external_id__isnull=False) & ~models.Q(external_id=""), name="int_ext_message_uniq"),
            models.UniqueConstraint(
                fields=["provider", "account_scope", "whatsapp_message"],
                condition=models.Q(whatsapp_message__isnull=False),
                name="int_msg_local_provider_uniq",
            ),
        ]


class AttachmentMapping(models.Model):
    evidence = models.ForeignKey("whatsapp.EvidenciaWhatsapp", null=True, blank=True, on_delete=models.SET_NULL)
    logical_message = models.ForeignKey(IntegrationMessage, null=True, blank=True, on_delete=models.SET_NULL)
    provider = models.CharField(max_length=30, choices=Provider.choices)
    external_scope = models.CharField(max_length=160, default="internal")
    external_attachment_id = models.CharField(max_length=255, null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    mime_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    sync_status = models.CharField(max_length=15, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    last_error = models.CharField(max_length=255, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "external_scope", "external_attachment_id"], condition=models.Q(external_attachment_id__isnull=False) & ~models.Q(external_attachment_id=""), name="int_ext_attachment_uniq")
        ]


class AgentMapping(models.Model):
    account = models.ForeignKey(ChatwootAccountMapping, on_delete=models.CASCADE)
    chatwoot_user_id = models.CharField(max_length=80, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    active = models.BooleanField(default=False)
    sync_status = models.CharField(max_length=15, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    last_error = models.CharField(max_length=255, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "chatwoot_user_id"], condition=models.Q(chatwoot_user_id__isnull=False) & ~models.Q(chatwoot_user_id=""), name="int_cw_agent_uniq"),
            models.UniqueConstraint(fields=["account", "user"], condition=models.Q(active=True, user__isnull=False), name="int_cw_active_user_uniq"),
        ]

    def clean(self):
        if self.active and (not self.chatwoot_user_id or not self.user_id or not self.account.active):
            raise ValidationError("Active agent mapping requires active account, external ID and Django user.")


class ContextCheckpoint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey("whatsapp.ConversacionWhatsApp", on_delete=models.CASCADE, related_name="context_checkpoints")
    control_version = models.PositiveBigIntegerField()
    last_public_message = models.ForeignKey(IntegrationMessage, null=True, blank=True, on_delete=models.SET_NULL)
    history_scope = models.JSONField(default=dict, blank=True)
    advisor_instruction = models.TextField(blank=True)
    resume_mode = models.CharField(max_length=20, choices=ResumeMode.choices, default=ResumeMode.WAIT_FOR_CUSTOMER)
    collected_data = models.JSONField(default=dict, blank=True)
    missing_data = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20,
        choices=CheckpointStatus.choices,
        default=CheckpointStatus.PENDING,
    )
    error_summary = models.CharField(max_length=255, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["conversation", "status", "created_at"], name="int_checkpoint_conv_idx")]
