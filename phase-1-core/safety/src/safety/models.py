"""Request and report shapes for POST /check."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_TEXT = 5_000
MAX_CONTENT = 10_000
MAX_STEPS = 50
MAX_STEP = 1_000
MAX_SUB_BLOCKS = 10


class SubBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["code", "logs", "steps"]
    content: str | None = Field(default=None, max_length=MAX_CONTENT)
    steps: list[str] | None = Field(default=None, max_length=MAX_STEPS)

    @model_validator(mode="after")
    def _shape(self) -> "SubBlock":
        """Check that the block has the right fields."""
        if self.kind == "steps":
            if self.steps is None or self.content is not None:
                raise ValueError("steps blocks carry 'steps', not 'content'")
            if any(len(step) > MAX_STEP for step in self.steps):
                raise ValueError(f"a step is longer than {MAX_STEP} characters")
        elif self.content is None or self.steps is not None:
            raise ValueError("code and logs blocks carry 'content', not 'steps'")
        return self


class CheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=MAX_TEXT)
    sub_blocks: list[SubBlock] = Field(default_factory=list, max_length=MAX_SUB_BLOCKS)
    secrets_only: bool = False


class Finding(BaseModel):
    """One problem."""

    check: Literal["limit", "secret", "pii", "dangerous_command", "package"]
    severity: Literal["block", "warn"]
    location: str
    kind: str
    start: int | None = None
    end: int | None = None


class SafetyReport(BaseModel):
    ok: bool
    over_limit: bool
    blocks: list[Finding]
    warnings: list[Finding]


MAX_TEXTS = 20
MAX_MASK_TEXT = 20_000


class MaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texts: list[str] = Field(max_length=MAX_TEXTS)
    names: list[Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{3,30}$")]] = Field(
        default_factory=list, max_length=50
    )

    @model_validator(mode="after")
    def _sizes(self) -> "MaskIn":
        """Check the request sizes."""
        if any(len(t) > MAX_MASK_TEXT for t in self.texts):
            raise ValueError(f"a text is longer than {MAX_MASK_TEXT} characters")
        return self


class MaskOut(BaseModel):
    texts: list[str]
    table: dict[str, str]
    secrets_removed: int
