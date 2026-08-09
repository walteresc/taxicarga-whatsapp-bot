class IntegrationDomainError(Exception):
    code = "INTEGRATION_ERROR"

    def __init__(self, message, *, current_version=None):
        super().__init__(message)
        self.current_version = current_version


class InvalidTransition(IntegrationDomainError):
    code = "INVALID_TRANSITION"


class VersionConflict(IntegrationDomainError):
    code = "VERSION_CONFLICT"


class ConversationOwned(IntegrationDomainError):
    code = "ALREADY_OWNED"


class IdempotencyConflict(IntegrationDomainError):
    code = "IDEMPOTENCY_CONFLICT"


class PrivateMessageBlocked(IntegrationDomainError):
    code = "PRIVATE_MESSAGE_BLOCKED"


class UnknownChannel(IntegrationDomainError):
    code = "UNKNOWN_CHANNEL"


class StaleGeneration(IntegrationDomainError):
    code = "STALE_GENERATION"


class PendingHumanOutbox(IntegrationDomainError):
    code = "PENDING_HUMAN_OUTBOX"
