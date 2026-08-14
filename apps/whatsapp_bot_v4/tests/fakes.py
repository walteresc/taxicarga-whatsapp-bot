from collections import deque

from ..ai.schemas import AgentOutput


class ScriptedAgent:
    def __init__(self, outputs):
        self.outputs = deque(outputs)
        self.calls = 0
        self.contexts = []

    def respond(self, context, repair_error=None):
        self.calls += 1
        self.contexts.append((context, repair_error))
        output = self.outputs.popleft()
        return output if isinstance(output, AgentOutput) else AgentOutput.model_validate(output)


def output(*, updates=None, corrections=None, requested=None, reply="Perfecto, continuemos.", question=False, action="continue"):
    return {
        "updates": updates or {},
        "corrections": corrections or {},
        "requested_fields": requested or [],
        "customer_question": {"asked": question, "topic": "cobertura" if question else None, "answered": question},
        "conversation_action": action,
        "reply": reply,
        "handoff_requested": False,
    }
