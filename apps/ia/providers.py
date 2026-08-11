from abc import ABC, abstractmethod
from dataclasses import dataclass
from time import perf_counter

from django.conf import settings
from openai import OpenAI


SUPPORTED_PROVIDERS = {"openai", "deepseek"}


class AIProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class AIResult:
    text: str
    provider: str
    model: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None


class AIProvider(ABC):
    name = ""

    def __init__(self, *, api_key, model, base_url=None, timeout=30, client_factory=OpenAI):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.client_factory = client_factory

    def _client(self):
        if not self.api_key:
            raise AIProviderError(f"Credencial ausente para provider {self.name}.")
        kwargs = {"api_key": self.api_key, "timeout": self.timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return self.client_factory(**kwargs)

    @abstractmethod
    def _request_options(self):
        raise NotImplementedError

    def generate(self, messages):
        started = perf_counter()
        response = self._client().responses.create(
            model=self.model,
            input=messages,
            **self._request_options(),
        )
        usage = getattr(response, "usage", None)
        return AIResult(
            text=(getattr(response, "output_text", "") or "").strip(),
            provider=self.name,
            model=self.model,
            latency_ms=(perf_counter() - started) * 1000,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )

    def generate_structured(self, messages, *, schema_model):
        started = perf_counter()
        response = self._client().responses.parse(
            model=self.model,
            input=messages,
            text_format=schema_model,
            **self._request_options(),
        )
        usage = getattr(response, "usage", None)
        parsed = getattr(response, "output_parsed", None)
        return AIResult(
            text=(
                parsed.model_dump_json()
                if hasattr(parsed, "model_dump_json")
                else (getattr(response, "output_text", "") or "").strip()
            ),
            provider=self.name,
            model=self.model,
            latency_ms=(perf_counter() - started) * 1000,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )


class OpenAIProvider(AIProvider):
    name = "openai"

    def _request_options(self):
        return {}


class DeepSeekProvider(AIProvider):
    name = "deepseek"

    def _request_options(self):
        return {"extra_body": {"thinking": {"type": "disabled"}}}


def provider_name_for(responsibility):
    if responsibility == "extraction":
        return settings.AI_EXTRACTION_PROVIDER
    if responsibility == "conversation":
        return settings.AI_CONVERSATION_PROVIDER
    raise AIProviderError(f"Responsabilidad IA desconocida: {responsibility}.")


def build_provider(responsibility, provider_name=None, client_factory=OpenAI):
    name = (provider_name or provider_name_for(responsibility)).strip().lower()
    if name not in SUPPORTED_PROVIDERS:
        raise AIProviderError(f"Provider IA no soportado: {name}.")

    suffix = responsibility.upper()
    if name == "openai":
        return OpenAIProvider(
            api_key=settings.OPENAI_API_KEY,
            model=getattr(settings, f"OPENAI_{suffix}_MODEL"),
            timeout=settings.AI_REQUEST_TIMEOUT_SECONDS,
            client_factory=client_factory,
        )
    return DeepSeekProvider(
        api_key=settings.DEEPSEEK_API_KEY,
        model=getattr(settings, f"DEEPSEEK_{suffix}_MODEL"),
        base_url=settings.DEEPSEEK_BASE_URL,
        timeout=settings.AI_REQUEST_TIMEOUT_SECONDS,
        client_factory=client_factory,
    )
