"""What the api sends the orchestrator, and what it gets back."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Strength = Literal["coding", "reasoning", "writing", "cheap"]
Handle = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{3,30}$")]


class ModelRef(BaseModel):
    """One of the person's saved models."""

    model_config = ConfigDict(extra="forbid")

    model_id: uuid.UUID
    provider: Literal["openrouter", "openai", "gemini", "anthropic"]
    model: str = Field(pattern=r"^[A-Za-z0-9._:/-]{2,100}$")
    label: str | None = Field(default=None, max_length=40)
    strengths: list[Strength] = Field(default_factory=list, max_length=4)
    key_ciphertext: str = Field(min_length=16, max_length=4096)

    @property
    def name(self) -> str:
        """The name shown for this model."""
        return self.label or self.model


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class RunIn(BaseModel):
    """One run request from the api."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")
    user_id: uuid.UUID
    system: str = Field(min_length=1, max_length=10_000)
    messages: list[Message] = Field(min_length=1, max_length=4)
    models: list[ModelRef] = Field(min_length=1, max_length=3)
    memory: list[Annotated[str, StringConstraints(max_length=300)]] = Field(
        default_factory=list, max_length=5
    )
    privacy: Literal["public", "private"] = "public"
    names: list[Handle] = Field(default_factory=list, max_length=50)
    trace: bool = True


class Part(BaseModel):
    """One sub-task of the plan, and which model answered it."""

    kind: Literal["explain", "code", "check", "opinion"]
    task: str
    model: str | None = None


class RunOut(BaseModel):
    run_id: uuid.UUID
    status: Literal["ready", "failed"]
    text: str | None = None
    reason: str | None = None
    plan: list[Part] = Field(default_factory=list)
    models_used: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    trace_ids: list[str] = Field(default_factory=list)


class ResumeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "edited", "discarded"]
