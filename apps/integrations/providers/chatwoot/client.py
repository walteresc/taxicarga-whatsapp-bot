from dataclasses import dataclass
import logging

import requests
from django.conf import settings

from .exceptions import (
    ChatwootAPIError,
    ChatwootAuthenticationError,
    ChatwootConfigurationError,
    ChatwootConnectionError,
    ChatwootNotFoundError,
    ChatwootRateLimitError,
    ChatwootTimeoutError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatwootConfig:
    enabled: bool
    base_url: str
    access_token: str
    account_id: str
    inbox_id: str = ""
    connect_timeout: float = 3.0
    read_timeout: float = 10.0

    @classmethod
    def from_settings(cls):
        config = cls(
            enabled=settings.CHATWOOT_ENABLED,
            base_url=settings.CHATWOOT_BASE_URL,
            access_token=settings.CHATWOOT_API_ACCESS_TOKEN,
            account_id=str(settings.CHATWOOT_ACCOUNT_ID),
            inbox_id=str(settings.CHATWOOT_INBOX_ID),
            connect_timeout=settings.CHATWOOT_CONNECT_TIMEOUT,
            read_timeout=settings.CHATWOOT_READ_TIMEOUT,
        )
        config.validate()
        return config

    def validate(self):
        if not self.enabled:
            return
        missing = [
            name for name, value in (
                ("CHATWOOT_BASE_URL", self.base_url),
                ("CHATWOOT_API_ACCESS_TOKEN", self.access_token),
                ("CHATWOOT_ACCOUNT_ID", self.account_id),
            ) if not value
        ]
        if missing:
            raise ChatwootConfigurationError(f"Missing Chatwoot settings: {', '.join(missing)}")
        if not self.base_url.startswith(("http://", "https://")):
            raise ChatwootConfigurationError("CHATWOOT_BASE_URL must be an HTTP(S) URL.")
        if not self.account_id.isdigit() or (self.inbox_id and not self.inbox_id.isdigit()):
            raise ChatwootConfigurationError("Chatwoot account and inbox IDs must be numeric.")
        if self.connect_timeout <= 0 or self.read_timeout <= 0:
            raise ChatwootConfigurationError("Chatwoot timeouts must be positive.")


class ChatwootClient:
    def __init__(self, config=None, session=None):
        self.config = config or ChatwootConfig.from_settings()
        self.config.validate()
        if not self.config.enabled:
            raise ChatwootConfigurationError("Chatwoot integration is disabled.")
        self.session = session or requests.Session()

    @property
    def headers(self):
        return {"api_access_token": self.config.access_token, "Content-Type": "application/json"}

    def _request(self, method, endpoint, *, json=None):
        url = f"{self.config.base_url}{endpoint}"
        try:
            response = self.session.request(
                method, url, headers=self.headers, json=json,
                timeout=(self.config.connect_timeout, self.config.read_timeout),
            )
        except requests.Timeout as exc:
            raise ChatwootTimeoutError("Chatwoot request timed out.", method=method, endpoint=endpoint) from exc
        except requests.ConnectionError as exc:
            raise ChatwootConnectionError("Chatwoot connection failed.", method=method, endpoint=endpoint) from exc
        except requests.RequestException as exc:
            raise ChatwootConnectionError("Chatwoot request failed.", method=method, endpoint=endpoint) from exc

        request_id = response.headers.get("X-Request-Id", "")
        context = {"method": method, "endpoint": endpoint, "status_code": response.status_code, "request_id": request_id}
        if response.status_code in {401, 403}:
            raise ChatwootAuthenticationError("Chatwoot rejected authentication or permissions.", **context)
        if response.status_code == 404:
            raise ChatwootNotFoundError("Chatwoot resource was not found.", **context)
        if response.status_code == 429:
            raise ChatwootRateLimitError("Chatwoot rate limit reached.", **context)
        if response.status_code >= 400:
            raise ChatwootAPIError("Chatwoot API returned an error.", **context)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ChatwootAPIError("Chatwoot returned invalid JSON.", **context) from exc
        if not isinstance(payload, (dict, list)):
            raise ChatwootAPIError("Chatwoot returned an unexpected JSON type.", **context)
        return payload

    def get_account(self):
        return self._request("GET", f"/api/v1/accounts/{self.config.account_id}")

    def list_inboxes(self):
        payload = self._request("GET", f"/api/v1/accounts/{self.config.account_id}/inboxes")
        return payload.get("payload", payload) if isinstance(payload, dict) else payload

    def get_inbox(self, inbox_id=None):
        target = str(inbox_id or self.config.inbox_id)
        if not target:
            raise ChatwootConfigurationError("CHATWOOT_INBOX_ID is not configured.")
        return self._request("GET", f"/api/v1/accounts/{self.config.account_id}/inboxes/{target}")

    def create_api_inbox(self, name):
        return self._request(
            "POST", f"/api/v1/accounts/{self.config.account_id}/inboxes",
            json={"name": name, "channel": {"type": "api"}},
        )

    def ensure_sandbox_inbox(self, name="TaxiCarga Sandbox"):
        if self.config.inbox_id:
            return self.get_inbox(), False
        for inbox in self.list_inboxes():
            if inbox.get("name") == name and inbox.get("channel_type") == "Channel::Api":
                return inbox, False
        return self.create_api_inbox(name), True

    def check(self):
        account = self.get_account()
        inbox = self.get_inbox() if self.config.inbox_id else None
        return account, inbox
