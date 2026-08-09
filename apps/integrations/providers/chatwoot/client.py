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

    def _request(self, method, endpoint, *, json=None, params=None):
        url = f"{self.config.base_url}{endpoint}"
        request_kwargs = {
            "headers": self.headers,
            "json": json,
            "timeout": (self.config.connect_timeout, self.config.read_timeout),
        }
        if params is not None:
            request_kwargs["params"] = params
        try:
            response = self.session.request(method, url, **request_kwargs)
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
        if response.status_code == 204 or not response.content:
            return {}
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

    def search_contacts(self, query):
        payload = self._request(
            "GET", f"/api/v1/accounts/{self.config.account_id}/contacts/search", params={"q": query}
        )
        return payload.get("payload", [])

    def get_contact(self, contact_id):
        return self._request("GET", f"/api/v1/accounts/{self.config.account_id}/contacts/{contact_id}")

    def create_contact(self, *, inbox_id, identifier, name, email=""):
        payload = {"inbox_id": int(inbox_id), "identifier": identifier, "name": name}
        if email:
            payload["email"] = email
        return self._request("POST", f"/api/v1/accounts/{self.config.account_id}/contacts", json=payload)

    def create_contact_inbox(self, *, contact_id, inbox_id, source_id):
        return self._request(
            "POST",
            f"/api/v1/accounts/{self.config.account_id}/contacts/{contact_id}/contact_inboxes",
            json={"inbox_id": int(inbox_id), "source_id": source_id},
        )

    def get_conversation(self, conversation_id):
        return self._request(
            "GET", f"/api/v1/accounts/{self.config.account_id}/conversations/{conversation_id}"
        )

    def list_conversations(self, *, inbox_id):
        payload = self._request(
            "GET", f"/api/v1/accounts/{self.config.account_id}/conversations",
            params={"inbox_id": int(inbox_id), "status": "all", "assignee_type": "all"},
        )
        return payload.get("data", {}).get("payload", [])

    def create_conversation(self, *, source_id, inbox_id, contact_id, canonical_id):
        return self._request(
            "POST", f"/api/v1/accounts/{self.config.account_id}/conversations",
            json={
                "source_id": source_id,
                "inbox_id": int(inbox_id),
                "contact_id": int(contact_id),
                "status": "open",
                "additional_attributes": {"taxicarga_conversation_id": canonical_id},
            },
        )

    def list_messages(self, conversation_id):
        payload = self._request(
            "GET", f"/api/v1/accounts/{self.config.account_id}/conversations/{conversation_id}/messages"
        )
        return payload.get("payload", [])

    def create_message(self, *, conversation_id, content, message_type, canonical_id):
        return self._request(
            "POST",
            f"/api/v1/accounts/{self.config.account_id}/conversations/{conversation_id}/messages",
            json={
                "content": content,
                "message_type": message_type,
                "private": False,
                "content_type": "text",
                "content_attributes": {
                    "taxicarga_message_id": canonical_id,
                    "taxicarga_origin": "django_projection",
                },
            },
        )

    def list_custom_attribute_definitions(self):
        payload = self._request(
            "GET", f"/api/v1/accounts/{self.config.account_id}/custom_attribute_definitions"
        )
        return payload.get("payload", payload) if isinstance(payload, dict) else payload

    def create_conversation_list_attribute(self, *, key, display_name, values):
        return self._request(
            "POST",
            f"/api/v1/accounts/{self.config.account_id}/custom_attribute_definitions",
            json={
                "attribute_display_name": display_name,
                "attribute_display_type": "list",
                "attribute_description": "Estado de control proyectado desde TaxiCarga.",
                "attribute_key": key,
                "attribute_model": "conversation_attribute",
                "attribute_values": values,
            },
        )

    def create_conversation_text_attribute(self, *, key, display_name):
        return self._request(
            "POST",
            f"/api/v1/accounts/{self.config.account_id}/custom_attribute_definitions",
            json={
                "attribute_display_name": display_name,
                "attribute_display_type": "text",
                "attribute_description": "Dato operativo proyectado desde TaxiCarga.",
                "attribute_key": key,
                "attribute_model": "conversation_attribute",
            },
        )

    def ensure_conversation_text_attribute(self, *, key, display_name):
        matches = [
            item for item in self.list_custom_attribute_definitions()
            if item.get("attribute_key") == key
            and item.get("attribute_model") == "conversation_attribute"
        ]
        if len(matches) > 1:
            raise ChatwootAPIError("Duplicate Chatwoot custom attribute definitions found.")
        if matches:
            return matches[0], False
        return self.create_conversation_text_attribute(key=key, display_name=display_name), True

    def ensure_conversation_list_attribute(self, *, key, display_name, values):
        matches = [
            item for item in self.list_custom_attribute_definitions()
            if item.get("attribute_key") == key
            and item.get("attribute_model") == "conversation_attribute"
        ]
        if len(matches) > 1:
            raise ChatwootAPIError("Duplicate Chatwoot custom attribute definitions found.")
        if matches:
            return matches[0], False
        return self.create_conversation_list_attribute(
            key=key, display_name=display_name, values=values
        ), True

    def update_conversation_custom_attributes(self, conversation_id, attributes):
        return self._request(
            "POST",
            f"/api/v1/accounts/{self.config.account_id}/conversations/{conversation_id}/custom_attributes",
            json={"custom_attributes": attributes},
        )

    def list_labels(self):
        payload = self._request("GET", f"/api/v1/accounts/{self.config.account_id}/labels")
        return payload.get("payload", payload) if isinstance(payload, dict) else payload

    def create_label(self, title, *, color="#1f93ff", description=""):
        return self._request(
            "POST", f"/api/v1/accounts/{self.config.account_id}/labels",
            json={"title": title, "color": color, "description": description},
        )

    def ensure_label(self, title):
        matches = [item for item in self.list_labels() if item.get("title") == title]
        if len(matches) > 1:
            raise ChatwootAPIError("Duplicate Chatwoot labels found.")
        if matches:
            return matches[0], False
        return self.create_label(title, description="Proyección comercial TaxiCarga"), True

    def set_conversation_labels(self, conversation_id, labels):
        return self._request(
            "POST",
            f"/api/v1/accounts/{self.config.account_id}/conversations/{conversation_id}/labels",
            json={"labels": sorted(set(labels))},
        )

    def list_webhooks(self):
        payload = self._request("GET", f"/api/v1/accounts/{self.config.account_id}/webhooks")
        if not isinstance(payload, dict):
            return payload
        items = payload.get("payload", payload)
        if isinstance(items, dict):
            return items.get("webhooks", [])
        return items

    def create_webhook(self, *, name, url, subscriptions):
        payload = self._request(
            "POST",
            f"/api/v1/accounts/{self.config.account_id}/webhooks",
            json={"name": name, "url": url, "subscriptions": subscriptions},
        )
        return self._webhook_payload(payload)

    def update_webhook(self, webhook_id, *, name, url, subscriptions):
        payload = self._request(
            "PUT",
            f"/api/v1/accounts/{self.config.account_id}/webhooks/{webhook_id}",
            json={"name": name, "url": url, "subscriptions": subscriptions},
        )
        return self._webhook_payload(payload)

    def delete_webhook(self, webhook_id):
        return self._request(
            "DELETE", f"/api/v1/accounts/{self.config.account_id}/webhooks/{webhook_id}"
        )

    @staticmethod
    def _webhook_payload(payload):
        item = payload.get("payload", payload) if isinstance(payload, dict) else payload
        if isinstance(item, dict):
            return item.get("webhook", item)
        return item

    def ensure_webhook(self, *, name, url, subscriptions):
        matches = [
            webhook for webhook in self.list_webhooks()
            if webhook.get("name") == name
        ]
        if matches:
            webhook = matches[0]
            if webhook.get("url") != url or sorted(webhook.get("subscriptions") or []) != sorted(subscriptions):
                webhook = self.update_webhook(
                    webhook["id"], name=name, url=url, subscriptions=subscriptions
                )
                return webhook, False, True
            return webhook, False, False
        return self.create_webhook(name=name, url=url, subscriptions=subscriptions), True, False
