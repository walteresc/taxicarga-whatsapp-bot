from unittest.mock import Mock

from ..adapters.meta import MetaSendResult, MetaV4Adapter


def meta_payload(text="Hola, necesito una mudanza", *, wamid="wamid.test.1", phone_number_id="meta-v4-test", customer="51911112222", message_type="text"):
    message = {
        "from": customer,
        "id": wamid,
        "timestamp": "1786665600",
        "type": message_type,
    }
    if message_type == "text":
        message["text"] = {"body": text}
    else:
        message[message_type] = {"id": "media-1"}
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": phone_number_id},
            "messages": [message],
        }}]}],
    }


class FakeMetaAdapter(MetaV4Adapter):
    def __init__(self, *, send_success=True):
        super().__init__(access_token="test-token")
        self.sent = []
        self.send_success = send_success

    def send_text(self, channel, message):
        self.sent.append((channel, message))
        if not self.send_success:
            return MetaSendResult(False, error_code="mock_error", error_message="safe failure")
        return MetaSendResult(True, f"wamid.out.{len(self.sent)}", 200)


class RecordingChatwoot:
    def __init__(self, *, allowed=True, fail_projection=False):
        self.allowed = allowed
        self.fail_projection = fail_projection
        self.customer_messages = []
        self.bot_messages = []

    def is_bot_allowed(self, _conversation):
        return self.allowed

    def project_customer_message(self, message):
        if self.fail_projection:
            raise RuntimeError("Chatwoot unavailable")
        self.customer_messages.append(message.pk)

    def project_bot_message(self, message):
        if self.fail_projection:
            raise RuntimeError("Chatwoot unavailable")
        self.bot_messages.append(message.pk)


def http_response(*, ok=True, status=200, payload=None):
    response = Mock()
    response.ok = ok
    response.status_code = status
    response.content = b"{}"
    response.json.return_value = payload or {}
    return response
