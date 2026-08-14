import json
from typing import Protocol

from django.conf import settings
from openai import OpenAI

from .prompts import REPAIR_PROMPT, RESPONSE_REPAIR_PROMPT, SYSTEM_PROMPT
from .schemas import AgentOutput


class ConversationAgent(Protocol):
    calls: int

    def respond(self, context: dict, repair_error: str | None = None) -> AgentOutput: ...


class OpenAIConversationAgent:
    def __init__(self, client=None, model: str | None = None):
        self.client = client or OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = model or settings.OPENAI_MODEL
        self.calls = 0

    def respond(self, context: dict, repair_error: str | None = None) -> AgentOutput:
        self.calls += 1
        instructions = SYSTEM_PROMPT
        if repair_error:
            instructions += "\n" + REPAIR_PROMPT.format(error=repair_error)
        if context.get("repair_scope") == "response_only":
            instructions += "\n" + RESPONSE_REPAIR_PROMPT
        response = self.client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=json.dumps(context, ensure_ascii=False),
            text_format=AgentOutput,
            temperature=0,
            max_output_tokens=900,
            store=False,
        )
        if response.output_parsed is None:
            raise ValueError("OpenAI no devolvió salida estructurada")
        return response.output_parsed
