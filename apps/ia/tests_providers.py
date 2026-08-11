import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from .openai_client import ExtractionSchemaError, extract_lead_with_ai, generate_reply
from .providers import AIProviderError, AIResult, DeepSeekProvider, OpenAIProvider, build_provider


class _Responses:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class _Factory:
    def __init__(self, responses):
        self.responses = responses
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(responses=self.responses)


class ProviderSelectionTests(SimpleTestCase):
    @override_settings(
        OPENAI_API_KEY="test-key",
        OPENAI_EXTRACTION_MODEL="gpt-4.1-mini",
        AI_REQUEST_TIMEOUT_SECONDS=12,
    )
    def test_openai_selection_and_model(self):
        provider = build_provider("extraction", "openai")
        self.assertIsInstance(provider, OpenAIProvider)
        self.assertEqual(provider.model, "gpt-4.1-mini")
        self.assertIsNone(provider.base_url)

    @override_settings(
        DEEPSEEK_API_KEY="test-key",
        DEEPSEEK_CONVERSATION_MODEL="deepseek-v4-flash",
        DEEPSEEK_BASE_URL="https://api.deepseek.com",
        AI_REQUEST_TIMEOUT_SECONDS=12,
    )
    def test_deepseek_selection_model_and_base_url(self):
        provider = build_provider("conversation", "deepseek")
        self.assertIsInstance(provider, DeepSeekProvider)
        self.assertEqual(provider.model, "deepseek-v4-flash")
        self.assertEqual(provider.base_url, "https://api.deepseek.com")

    @override_settings(
        AI_EXTRACTION_PROVIDER="openai",
        AI_CONVERSATION_PROVIDER="deepseek",
        OPENAI_API_KEY="test-key",
        DEEPSEEK_API_KEY="test-key",
        OPENAI_EXTRACTION_MODEL="gpt-4.1-mini",
        DEEPSEEK_CONVERSATION_MODEL="deepseek-v4-flash",
        DEEPSEEK_BASE_URL="https://api.deepseek.com",
        AI_REQUEST_TIMEOUT_SECONDS=12,
    )
    def test_responsibilities_select_independently(self):
        self.assertIsInstance(build_provider("extraction"), OpenAIProvider)
        self.assertIsInstance(build_provider("conversation"), DeepSeekProvider)

    def test_unknown_provider_fails_closed(self):
        with self.assertRaises(AIProviderError):
            build_provider("conversation", "unknown")


class ProviderRequestTests(SimpleTestCase):
    def _response(self, text="ok"):
        return SimpleNamespace(
            output_text=text,
            usage=SimpleNamespace(input_tokens=10, output_tokens=4),
        )

    def test_openai_uses_responses_without_behavior_changes(self):
        responses = _Responses(self._response())
        factory = _Factory(responses)
        provider = OpenAIProvider(api_key="test-key", model="gpt-4.1-mini", client_factory=factory)
        result = provider.generate([{"role": "user", "content": "hola"}])
        self.assertEqual(result.text, "ok")
        self.assertNotIn("extra_body", responses.calls[0])
        self.assertEqual(responses.calls[0]["model"], "gpt-4.1-mini")

    def test_deepseek_disables_thinking_and_drops_reasoning(self):
        response = self._response("respuesta final")
        response.reasoning_content = "contenido que no debe persistirse"
        responses = _Responses(response)
        factory = _Factory(responses)
        provider = DeepSeekProvider(
            api_key="test-key",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            client_factory=factory,
        )
        result = provider.generate([{"role": "user", "content": "hola"}])
        self.assertEqual(result.text, "respuesta final")
        self.assertFalse(hasattr(result, "reasoning_content"))
        self.assertEqual(responses.calls[0]["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertEqual(factory.kwargs["base_url"], "https://api.deepseek.com")

    def test_timeout_propagates_to_caller(self):
        provider = OpenAIProvider(
            api_key="test-key",
            model="gpt-4.1-mini",
            client_factory=_Factory(_Responses(error=TimeoutError("timeout"))),
        )
        with self.assertRaises(TimeoutError):
            provider.generate([])

    def test_secret_absent_fails_before_http(self):
        factory = Mock()
        provider = OpenAIProvider(api_key="", model="gpt-4.1-mini", client_factory=factory)
        with self.assertRaises(AIProviderError):
            provider.generate([])
        factory.assert_not_called()


class CommonContractTests(SimpleTestCase):
    def _result(self, text, provider="openai"):
        return AIResult(text, provider, "model", 1.2, 20, 8)

    def test_extraction_contract_is_provider_independent(self):
        payload = json.dumps({
            "campos_detectados": {"lista_objetos": "15 cajas"},
            "faltantes": [],
            "confianza": "alta",
        })
        lead = SimpleNamespace()
        for provider_name in ("openai", "deepseek"):
            provider = Mock()
            provider.generate.return_value = self._result(payload, provider_name)
            with patch("apps.ia.openai_client.build_provider", return_value=provider):
                result = extract_lead_with_ai("Tengo 15 cajas", lead, provider_name=provider_name)
            self.assertEqual(result["campos_detectados"], {"lista_objetos": "15 cajas"})
            self.assertNotIn("piso_origen", result["campos_detectados"])
            self.assertEqual(result["metrics"]["provider"], provider_name)

    def test_generator_contract_is_provider_independent(self):
        for provider_name in ("openai", "deepseek"):
            provider = Mock()
            provider.generate.return_value = self._result("Respuesta breve", provider_name)
            with patch("apps.ia.openai_client.build_provider", return_value=provider):
                self.assertEqual(generate_reply([{"role": "user", "content": "hola"}]), "Respuesta breve")

    def test_invalid_extraction_json_is_classified_as_schema_error(self):
        provider = Mock()
        provider.generate.return_value = self._result("no es json")
        with patch("apps.ia.openai_client.build_provider", return_value=provider):
            with self.assertRaises(ExtractionSchemaError):
                extract_lead_with_ai("hola", SimpleNamespace(), raise_errors=True)

    def test_api_error_uses_local_fallback_without_second_provider(self):
        with patch("apps.ia.openai_client.build_provider", side_effect=TimeoutError("timeout")) as build:
            self.assertIsNone(generate_reply([{"role": "user", "content": "hola"}]))
        self.assertEqual(build.call_count, 1)

    def test_harness_validate_only_never_calls_provider(self):
        with patch("apps.ia.management.commands.evaluate_ai_providers.extract_lead_with_ai") as extract:
            call_command("evaluate_ai_providers", "--validate-only")
        extract.assert_not_called()
