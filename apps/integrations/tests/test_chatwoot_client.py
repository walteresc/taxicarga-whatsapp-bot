from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from apps.integrations.providers.chatwoot.client import ChatwootClient, ChatwootConfig
from apps.integrations.providers.chatwoot.exceptions import (
    ChatwootAPIError,
    ChatwootAuthenticationError,
    ChatwootConfigurationError,
    ChatwootConnectionError,
    ChatwootNotFoundError,
    ChatwootRateLimitError,
    ChatwootTimeoutError,
)


def config(**overrides):
    values = {
        "enabled": True,
        "base_url": "https://chatwoot.test",
        "access_token": "secret-token",
        "account_id": "7",
        "inbox_id": "",
        "connect_timeout": 2.0,
        "read_timeout": 8.0,
    }
    values.update(overrides)
    return ChatwootConfig(**values)


def response(status=200, payload=None):
    result = Mock(status_code=status, headers={"X-Request-Id": "request-1"})
    result.content = b"{}"
    result.json.return_value = {} if payload is None else payload
    return result


class ChatwootConfigurationTests(SimpleTestCase):
    @override_settings(
        CHATWOOT_ENABLED=False,
        CHATWOOT_BASE_URL="",
        CHATWOOT_API_ACCESS_TOKEN="",
        CHATWOOT_ACCOUNT_ID="",
        CHATWOOT_INBOX_ID="",
        CHATWOOT_CONNECT_TIMEOUT=3.0,
        CHATWOOT_READ_TIMEOUT=10.0,
    )
    def test_disabled_configuration_accepts_empty_values_and_makes_no_call(self):
        session = Mock()
        loaded = ChatwootConfig.from_settings()

        with self.assertRaisesRegex(ChatwootConfigurationError, "disabled"):
            ChatwootClient(config=loaded, session=session)

        session.request.assert_not_called()

    def test_enabled_configuration_requires_all_core_values(self):
        with self.assertRaisesRegex(ChatwootConfigurationError, "CHATWOOT_API_ACCESS_TOKEN"):
            config(access_token="").validate()

    def test_enabled_configuration_validates_url_ids_and_timeouts(self):
        invalid = (
            config(base_url="chatwoot.test"),
            config(account_id="account"),
            config(inbox_id="inbox"),
            config(connect_timeout=0),
        )
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ChatwootConfigurationError):
                item.validate()


class ChatwootHTTPTests(SimpleTestCase):
    def test_get_account_uses_expected_path_header_and_timeouts(self):
        session = Mock()
        session.request.return_value = response(payload={"id": 7})

        payload = ChatwootClient(config=config(), session=session).get_account()

        self.assertEqual(payload, {"id": 7})
        session.request.assert_called_once_with(
            "GET",
            "https://chatwoot.test/api/v1/accounts/7",
            headers={"api_access_token": "secret-token", "Content-Type": "application/json"},
            json=None,
            timeout=(2.0, 8.0),
        )

    def test_get_and_list_inbox_paths(self):
        session = Mock()
        session.request.side_effect = [
            response(payload={"payload": [{"id": 4}]}),
            response(payload={"id": 4}),
        ]
        client = ChatwootClient(config=config(inbox_id="4"), session=session)

        self.assertEqual(client.list_inboxes(), [{"id": 4}])
        self.assertEqual(client.get_inbox(), {"id": 4})
        self.assertIn("/api/v1/accounts/7/inboxes/4", session.request.call_args_list[1].args[1])

    def test_create_api_inbox_payload(self):
        session = Mock()
        session.request.return_value = response(payload={"id": 9})

        ChatwootClient(config=config(), session=session).create_api_inbox("Sandbox")

        self.assertEqual(session.request.call_args.kwargs["json"], {
            "name": "Sandbox",
            "channel": {"type": "api"},
        })

    def test_http_statuses_raise_typed_safe_errors(self):
        cases = (
            (401, ChatwootAuthenticationError),
            (403, ChatwootAuthenticationError),
            (404, ChatwootNotFoundError),
            (429, ChatwootRateLimitError),
            (500, ChatwootAPIError),
        )
        for status, exception in cases:
            session = Mock()
            session.request.return_value = response(status=status)
            with self.subTest(status=status), self.assertRaises(exception) as caught:
                ChatwootClient(config=config(), session=session).get_account()
            rendered = str(caught.exception)
            self.assertNotIn("secret-token", rendered)
            self.assertEqual(caught.exception.status_code, status)

    def test_network_errors_are_typed(self):
        cases = (
            (requests.Timeout(), ChatwootTimeoutError),
            (requests.ConnectionError(), ChatwootConnectionError),
            (requests.RequestException(), ChatwootConnectionError),
        )
        for error, exception in cases:
            session = Mock()
            session.request.side_effect = error
            with self.subTest(error=error), self.assertRaises(exception):
                ChatwootClient(config=config(), session=session).get_account()

    def test_invalid_json_and_unexpected_json_type_are_rejected(self):
        invalid_json = response()
        invalid_json.json.side_effect = ValueError("bad json")
        scalar_json = response(payload="not-an-object")
        for result in (invalid_json, scalar_json):
            session = Mock()
            session.request.return_value = result
            with self.assertRaises(ChatwootAPIError):
                ChatwootClient(config=config(), session=session).get_account()

    def test_webhook_is_created_with_only_message_created(self):
        session = Mock()
        session.request.side_effect = [
            response(payload={"payload": {"webhooks": []}}),
            response(payload={"payload": {"webhook": {"id": 8, "secret": "generated"}}}),
        ]
        client = ChatwootClient(config=config(), session=session)

        webhook, created, updated = client.ensure_webhook(
            name="TaxiCarga Django Sandbox",
            url="https://django.test/webhooks/chatwoot/",
            subscriptions=["message_created"],
        )

        self.assertEqual(webhook["id"], 8)
        self.assertTrue(created)
        self.assertFalse(updated)
        self.assertEqual(session.request.call_args_list[1].kwargs["json"]["subscriptions"], ["message_created"])

    def test_webhook_is_reused_and_subscription_corrected(self):
        existing = {
            "id": 8,
            "name": "TaxiCarga Django Sandbox",
            "url": "https://django.test/webhooks/chatwoot/",
            "subscriptions": ["message_created", "conversation_created"],
        }
        session = Mock()
        session.request.side_effect = [
            response(payload={"payload": {"webhooks": [existing]}}),
            response(payload={"payload": {"webhook": {**existing, "subscriptions": ["message_created"]}}}),
        ]
        client = ChatwootClient(config=config(), session=session)

        _webhook, created, updated = client.ensure_webhook(
            name=existing["name"], url=existing["url"], subscriptions=["message_created"]
        )

        self.assertFalse(created)
        self.assertTrue(updated)
        self.assertEqual(session.request.call_args_list[1].args[0], "PUT")

    def test_webhook_url_change_updates_same_named_webhook(self):
        existing = {
            "id": 8, "name": "TaxiCarga Django Sandbox",
            "url": "http://old.test/webhooks/chatwoot/", "subscriptions": ["message_created"],
        }
        session = Mock()
        session.request.side_effect = [
            response(payload={"payload": {"webhooks": [existing]}}),
            response(payload={"payload": {"webhook": {**existing, "url": "https://new.test/webhooks/chatwoot/"}}}),
        ]
        client = ChatwootClient(config=config(), session=session)

        _webhook, created, updated = client.ensure_webhook(
            name=existing["name"], url="https://new.test/webhooks/chatwoot/", subscriptions=["message_created"]
        )

        self.assertFalse(created)
        self.assertTrue(updated)
        self.assertEqual(session.request.call_args_list[1].args[0], "PUT")

    def test_empty_success_response_is_accepted_for_delete(self):
        session = Mock()
        empty = response()
        empty.content = b""
        session.request.return_value = empty

        result = ChatwootClient(config=config(), session=session).delete_webhook(8)

        self.assertEqual(result, {})
        self.assertEqual(session.request.call_args.args[0], "DELETE")


class ChatwootSandboxTests(SimpleTestCase):
    def test_configured_inbox_is_reused_without_list_or_create(self):
        client = ChatwootClient(config=config(inbox_id="4"), session=Mock())
        with patch.object(client, "get_inbox", return_value={"id": 4}) as get_inbox, \
                patch.object(client, "list_inboxes") as list_inboxes, \
                patch.object(client, "create_api_inbox") as create:
            inbox, created = client.ensure_sandbox_inbox()

        self.assertEqual(inbox, {"id": 4})
        self.assertFalse(created)
        get_inbox.assert_called_once_with()
        list_inboxes.assert_not_called()
        create.assert_not_called()

    def test_existing_api_inbox_is_reused_idempotently(self):
        client = ChatwootClient(config=config(), session=Mock())
        existing = {"id": 5, "name": "TaxiCarga Sandbox", "channel_type": "Channel::Api"}
        with patch.object(client, "list_inboxes", return_value=[existing]) as list_inboxes, \
                patch.object(client, "create_api_inbox") as create:
            first = client.ensure_sandbox_inbox()
            second = client.ensure_sandbox_inbox()

        self.assertEqual(first, (existing, False))
        self.assertEqual(second, (existing, False))
        self.assertEqual(list_inboxes.call_count, 2)
        create.assert_not_called()

    def test_missing_inbox_is_created_once_per_setup_call(self):
        client = ChatwootClient(config=config(), session=Mock())
        created_inbox = {"id": 6, "name": "TaxiCarga Sandbox"}
        with patch.object(client, "list_inboxes", return_value=[]), \
                patch.object(client, "create_api_inbox", return_value=created_inbox) as create:
            result = client.ensure_sandbox_inbox()

        self.assertEqual(result, (created_inbox, True))
        create.assert_called_once_with("TaxiCarga Sandbox")


class ChatwootCommandTests(SimpleTestCase):
    @patch("apps.integrations.management.commands.chatwoot_check.ChatwootClient")
    def test_check_command_reports_account_without_secret(self, client_class):
        client_class.return_value.check.return_value = ({"id": 7, "name": "Test"}, None)
        output = StringIO()

        call_command("chatwoot_check", stdout=output)

        self.assertIn("CHATWOOT OK", output.getvalue())
        self.assertNotIn("secret-token", output.getvalue())

    @patch("apps.integrations.management.commands.chatwoot_setup_sandbox.ChatwootClient")
    def test_setup_command_reports_reuse(self, client_class):
        client_class.return_value.ensure_sandbox_inbox.return_value = (
            {"id": 5, "name": "Sandbox", "channel_type": "Channel::Api"},
            False,
        )
        output = StringIO()

        call_command("chatwoot_setup_sandbox", stdout=output)

        self.assertIn("action=reused", output.getvalue())

    @patch("apps.integrations.management.commands.chatwoot_check.ChatwootClient")
    def test_command_maps_safe_client_error(self, client_class):
        client_class.side_effect = ChatwootConfigurationError("Chatwoot integration is disabled.")

        with self.assertRaises(CommandError):
            call_command("chatwoot_check", stdout=StringIO(), stderr=StringIO())

    @patch("apps.integrations.management.commands.chatwoot_setup_webhook.ChatwootClient")
    def test_webhook_setup_writes_secret_without_printing_it(self, client_class):
        client_class.return_value.ensure_webhook.return_value = (
            {"id": 8, "secret": "generated-webhook-secret"}, True, False
        )
        output = StringIO()
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("CHATWOOT_WEBHOOK_ENABLED=false\n", encoding="utf-8")
            call_command(
                "chatwoot_setup_webhook",
                "https://django.test/webhooks/chatwoot/",
                env_file=str(env_file),
                stdout=output,
            )
            content = env_file.read_text(encoding="utf-8")

        self.assertIn("CHATWOOT_WEBHOOK_ENABLED=true", content)
        self.assertIn("CHATWOOT_WEBHOOK_SECRET=generated-webhook-secret", content)
        self.assertIn("ALLOWED_HOSTS=django.test", content)
        self.assertNotIn("generated-webhook-secret", output.getvalue())

    @patch("apps.integrations.management.commands.chatwoot_setup_webhook.ChatwootClient")
    def test_reused_webhook_without_returned_secret_preserves_local_secret(self, client_class):
        client_class.return_value.ensure_webhook.return_value = ({"id": 8, "secret": ""}, False, False)
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("CHATWOOT_WEBHOOK_SECRET=existing-local-secret\n", encoding="utf-8")
            call_command(
                "chatwoot_setup_webhook",
                "https://django.test/webhooks/chatwoot/",
                env_file=str(env_file),
                stdout=StringIO(),
            )
            content = env_file.read_text(encoding="utf-8")

        self.assertIn("CHATWOOT_WEBHOOK_SECRET=existing-local-secret", content)
