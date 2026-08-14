from dataclasses import dataclass
from datetime import datetime, timezone

import requests
from django.conf import settings


class MetaV4Error(RuntimeError):
    pass


class MetaPayloadError(MetaV4Error):
    pass


@dataclass(frozen=True)
class InboundMessage:
    external_message_id: str
    channel_id: str
    customer_id: str
    text: str
    timestamp: datetime | None
    message_type: str


@dataclass(frozen=True)
class OutboundMessage:
    customer_id: str
    text: str
    conversation_id: int


@dataclass(frozen=True)
class MetaSendResult:
    sent: bool
    external_message_id: str = ""
    status_code: int | None = None
    error_code: str = ""
    error_message: str = ""


class MetaV4Adapter:
    def __init__(self, *, session=None, access_token=None, api_version=None, timeout=8):
        self.session = session or requests.Session()
        self.access_token = settings.WHATSAPP_ACCESS_TOKEN if access_token is None else access_token
        self.api_version = api_version or settings.WHATSAPP_API_VERSION
        self.timeout = timeout

    @staticmethod
    def parse_inbound(payload) -> InboundMessage | None:
        if not isinstance(payload, dict):
            raise MetaPayloadError("Payload Meta debe ser objeto JSON")
        try:
            value = payload["entry"][0]["changes"][0]["value"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MetaPayloadError("Estructura Meta inválida") from exc
        messages = value.get("messages")
        if not messages:
            return None
        message = messages[0]
        message_type = str(message.get("type") or "")
        if message_type != "text":
            return None
        metadata = value.get("metadata") or {}
        external_id = str(message.get("id") or "").strip()
        channel_id = str(metadata.get("phone_number_id") or "").strip()
        customer_id = str(message.get("from") or "").strip()
        text = str((message.get("text") or {}).get("body") or "").strip()
        if not all((external_id, channel_id, customer_id, text)):
            raise MetaPayloadError("Mensaje Meta text incompleto")
        raw_timestamp = message.get("timestamp")
        timestamp = None
        if raw_timestamp:
            try:
                timestamp = datetime.fromtimestamp(int(raw_timestamp), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                timestamp = None
        return InboundMessage(external_id, channel_id, customer_id, text, timestamp, message_type)

    def send_text(self, channel, message: OutboundMessage) -> MetaSendResult:
        if not channel.activo or not channel.phone_number_id or not self.access_token:
            return MetaSendResult(False, error_code="missing_configuration", error_message="Meta V4 no configurado")
        url = f"https://graph.facebook.com/{self.api_version}/{channel.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": message.customer_id,
            "type": "text",
            "text": {"body": message.text},
        }
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
            data = response.json() if response.content else {}
            if not response.ok:
                error = data.get("error") if isinstance(data, dict) else {}
                return MetaSendResult(
                    False,
                    status_code=response.status_code,
                    error_code=str((error or {}).get("code") or "http_error"),
                    error_message=str((error or {}).get("message") or "Meta HTTP error")[:240],
                )
            wamid = str(((data.get("messages") or [{}])[0]).get("id") or "")
            if not wamid:
                return MetaSendResult(False, status_code=response.status_code, error_code="missing_wamid", error_message="Meta no devolvió WAMID")
            return MetaSendResult(True, wamid, response.status_code)
        except (requests.RequestException, ValueError) as exc:
            return MetaSendResult(False, error_code="request_error", error_message=exc.__class__.__name__)

    def check_auth(self, phone_number_id: str) -> bool:
        if not self.access_token or not phone_number_id:
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{phone_number_id}"
        response = self.session.get(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            params={"fields": "id"},
            timeout=self.timeout,
        )
        return response.ok and str((response.json() or {}).get("id") or "") == str(phone_number_id)
