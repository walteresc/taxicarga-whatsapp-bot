class ChatwootError(Exception):
    kind = "api"

    def __init__(self, message, *, method="", endpoint="", status_code=None, request_id=""):
        super().__init__(message)
        self.method = method
        self.endpoint = endpoint
        self.status_code = status_code
        self.request_id = request_id


class ChatwootConfigurationError(ChatwootError):
    kind = "configuration"


class ChatwootAuthenticationError(ChatwootError):
    kind = "authentication"


class ChatwootNotFoundError(ChatwootError):
    kind = "not_found"


class ChatwootRateLimitError(ChatwootError):
    kind = "rate_limit"


class ChatwootConnectionError(ChatwootError):
    kind = "connection"


class ChatwootTimeoutError(ChatwootError):
    kind = "timeout"


class ChatwootAPIError(ChatwootError):
    kind = "api"
