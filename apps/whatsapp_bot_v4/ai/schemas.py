from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationAction(str, Enum):
    CONTINUE = "continue"
    NEW_QUOTE = "new_quote"
    CORRECTION = "correction"
    ACK = "ack"
    QUESTION = "question"


class CustomerQuestion(BaseModel):
    asked: bool = False
    topic: str | None = None
    answered: bool = False


class StatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_district: str | None = Field(None, description="Distrito desde donde sale la mudanza; señales: origen, desde, salgo/sale.")
    destination_district: str | None = Field(None, description="Distrito adonde llega la mudanza; señales: destino, hacia, voy a, llego/llega.")
    origin_floor: int | None = Field(None, description="Piso desde donde sale la carga. 'Salgo/sale del tercero' es origin_floor=3. Nunca usar 'llego/llega' aquí.")
    destination_floor: int | None = Field(None, description="Piso adonde llega la carga. 'Llego/llega al cuarto' es destination_floor=4. Nunca usar 'salgo/sale' aquí.")
    origin_access: Literal["ascensor", "escaleras", "NOT_APPLICABLE"] | None = Field(None, description="Acceso asociado explícitamente al origen/salida.")
    destination_access: Literal["ascensor", "escaleras", "NOT_APPLICABLE"] | None = Field(None, description="Acceso asociado explícitamente al destino/llegada.")
    items: list[str] | None = Field(None, description="Todos los objetos/carga explícitos en mensaje actual.")
    packing_modalidad: str | None = Field(None, description="Modalidad de embalaje solicitado por cliente: 'embalaje basico', 'embalaje premium', etc. Extraer solo si cliente menciona explícitamente embalaje.")

    def explicit_values(self) -> dict:
        return {
            key: value
            for key, value in self.model_dump(exclude_none=True).items()
            if value not in ("", [])
        }


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updates: StatePatch = Field(default_factory=StatePatch)
    corrections: StatePatch = Field(default_factory=StatePatch)
    requested_fields: list[str] = Field(default_factory=list)
    customer_question: CustomerQuestion = Field(default_factory=CustomerQuestion)
    conversation_action: ConversationAction = ConversationAction.CONTINUE
    reply: str = Field(min_length=1, max_length=1200)
    handoff_requested: bool = False
