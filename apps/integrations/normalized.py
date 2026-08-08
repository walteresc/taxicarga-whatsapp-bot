from dataclasses import dataclass, field
from datetime import datetime
from numbers import Real
from typing import Any
from uuid import UUID

from django.utils import timezone

from .enums import AuthorType, ContentType, Direction, ProcessingStatus, Provider, Visibility
from .errors import PrivateMessageBlocked


ALLOWED_METADATA = {
    "interaction_id", "interaction_type", "mime_type", "sha256", "caption",
    "source", "echo", "linked_device", "phone_number_id",
}


@dataclass(frozen=True)
class NormalizedAttachment:
    attachment_id: str
    media_type: str
    size: int | None = None
    sha256: str = ""
    storage_ref: str = ""

    def __post_init__(self):
        if not isinstance(self.attachment_id, str) or not self.attachment_id.strip():
            raise ValueError("Attachment identifiers are required.")
        if not isinstance(self.media_type, str) or not self.media_type.strip():
            raise ValueError("Attachment identifiers are required.")
        if self.size is not None and (not isinstance(self.size, int) or isinstance(self.size, bool) or self.size < 0):
            raise ValueError("Attachment size cannot be negative.")
        if not isinstance(self.sha256, str) or not isinstance(self.storage_ref, str):
            raise ValueError("Attachment references must be strings.")


@dataclass(frozen=True)
class NormalizedMessage:
    logical_message_id: UUID
    provider: str
    external_message_id: str
    account_ref: str
    channel_ref: str
    inbox_ref: str | None
    conversation_ref: str
    sender_ref: str
    recipient_ref: str | None
    direction: Direction
    author_ref: str | None
    author_type: AuthorType
    content_type: ContentType
    text: str = ""
    attachments: tuple[NormalizedAttachment, ...] = ()
    location: tuple[float, float] | None = None
    reply_to: str | None = None
    visibility: str = "private"
    external_timestamp: datetime | None = None
    received_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    correlation_id: UUID | None = None
    processing_status: ProcessingStatus = ProcessingStatus.NORMALIZED

    def __post_init__(self):
        if not isinstance(self.logical_message_id, UUID):
            raise ValueError("logical_message_id must be UUID.")
        if self.correlation_id is not None and not isinstance(self.correlation_id, UUID):
            raise ValueError("correlation_id must be UUID.")
        required = [self.channel_ref, self.conversation_ref, self.sender_ref, self.idempotency_key]
        if any(not isinstance(value, str) or not value.strip() for value in required):
            raise ValueError("Normalized message identifiers are required.")
        for optional in (self.external_message_id, self.account_ref, self.inbox_ref, self.recipient_ref, self.author_ref, self.reply_to):
            if optional is not None and not isinstance(optional, str):
                raise ValueError("Message references must be strings.")
        if self.reply_to is not None and not self.reply_to.strip():
            raise ValueError("reply_to cannot be empty.")
        if self.provider not in Provider.values:
            raise ValueError("Invalid provider.")
        if self.provider != Provider.INTERNAL and not self.external_message_id.strip():
            raise ValueError("External providers require external_message_id.")
        if self.direction not in Direction.values or self.author_type not in AuthorType.values:
            raise ValueError("Invalid direction or author.")
        if self.content_type not in ContentType.values or self.processing_status not in ProcessingStatus.values:
            raise ValueError("Invalid content type or processing status.")
        if self.visibility not in Visibility.values:
            raise ValueError("Invalid message visibility.")
        if not isinstance(self.text, str):
            raise ValueError("Message text must be a string.")
        if not isinstance(self.attachments, tuple) or not all(isinstance(item, NormalizedAttachment) for item in self.attachments):
            raise ValueError("Attachments must be a tuple of NormalizedAttachment.")
        if not isinstance(self.metadata, dict) or not all(isinstance(key, str) for key in self.metadata):
            raise ValueError("Metadata must be a dictionary with string keys.")
        unknown = set(self.metadata) - ALLOWED_METADATA
        if unknown:
            raise ValueError("Metadata contains unsupported keys.")
        if self.content_type == ContentType.LOCATION:
            if self.location is None:
                raise ValueError("Location content requires coordinates.")
            if not isinstance(self.location, tuple) or len(self.location) != 2:
                raise ValueError("Location must be a latitude/longitude tuple.")
            lat, lon = self.location
            if any(not isinstance(value, Real) or isinstance(value, bool) for value in (lat, lon)):
                raise ValueError("Coordinates must be numeric.")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Invalid coordinates.")
        if self.content_type in {ContentType.IMAGE, ContentType.AUDIO, ContentType.DOCUMENT, ContentType.VIDEO} and not self.attachments:
            raise ValueError("Media content requires an attachment.")
        if self.content_type == ContentType.INTERACTIVE_REPLY and not all(
            isinstance(self.metadata.get(key), str) and self.metadata[key].strip()
            for key in ("interaction_id", "interaction_type")
        ):
            raise ValueError("Interactive replies require interaction metadata.")
        for timestamp in (self.external_timestamp, self.received_at):
            if timestamp is not None and (not isinstance(timestamp, datetime) or not timezone.is_aware(timestamp)):
                raise ValueError("Timestamps must be timezone-aware datetimes.")
        valid_authors = {
            Direction.INBOUND: {AuthorType.CUSTOMER, AuthorType.UNKNOWN},
            Direction.OUTBOUND: {AuthorType.BOT, AuthorType.AGENT, AuthorType.EXTERNAL_HUMAN, AuthorType.SYSTEM},
            Direction.INTERNAL: {AuthorType.SYSTEM, AuthorType.AGENT, AuthorType.BOT},
        }
        if self.author_type not in valid_authors[self.direction]:
            raise ValueError("Direction and author are inconsistent.")

    def assert_public_delivery(self):
        if self.visibility != "public":
            raise PrivateMessageBlocked("Private messages cannot be delivered or used as bot context.")

    def public_context_text(self):
        self.assert_public_delivery()
        return self.text
