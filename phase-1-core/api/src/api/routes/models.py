"""The signed-in user's own model connections (Phase 2: up to 3, each with strength tags)."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    model_validator,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api import kms, ratelimit
from api.auth import CurrentUser, current_user
from api.config import get_settings
from api.validation import visible_text_only

router = APIRouter(prefix="/me/models")

SAVE_LIMIT = 10
SAVE_WINDOW_SECONDS = 3600
MAX_MODELS = 3
_TOO_MANY = f"You can save up to {MAX_MODELS} models; delete one first"
_DUPLICATE = "You already saved this model"
KEY_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")

Provider = Literal["openrouter", "openai", "gemini", "anthropic"]
Strength = Literal["coding", "reasoning", "writing", "cheap"]


def _key_chars(value: SecretStr) -> SecretStr:
    """Check that an API key has only allowed characters."""
    if not set(value.get_secret_value()) <= KEY_CHARS:
        raise ValueError("API keys contain only letters, digits, '.', '_' and '-'")
    return value


def _unique(values: list[Strength]) -> list[Strength]:
    """Check that no value is listed twice."""
    if len(set(values)) != len(values):
        raise ValueError("each strength once")
    return values


ApiKey = Annotated[SecretStr, Field(min_length=20, max_length=300), AfterValidator(_key_chars)]
Label = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    AfterValidator(visible_text_only),
]
Strengths = Annotated[list[Strength], Field(max_length=4), AfterValidator(_unique)]


class ModelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Provider
    model: str = Field(pattern=r"^[A-Za-z0-9._:/-]{2,100}$")
    api_key: ApiKey
    label: Label | None = None
    strengths: Strengths = []

    @model_validator(mode="after")
    def _free_only_in_beta(self) -> "ModelIn":
        """During beta, only free OpenRouter models are allowed."""
        if (
            get_settings().free_models_only
            and self.provider == "openrouter"
            and not self.model.endswith(":free")
        ):
            raise ValueError("during beta, OpenRouter models must be ':free' ones")
        return self


class ModelPatch(BaseModel):
    """The key cannot be changed: delete the model and save it again."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    label: Label | None = None
    strengths: Strengths | None = None


class ModelOut(BaseModel):
    id: uuid.UUID
    provider: str
    model: str
    label: str | None
    strengths: list[str]
    enabled: bool
    key_last4: str
    created_at: datetime


def _human(user: CurrentUser) -> None:
    """Only the person, not an AI app, may do this."""
    if user.actor != "human":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only you can manage your model keys")


@router.get("")
async def list_models(
    request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> list[ModelOut]:
    """List my saved models."""
    async with request.app.state.db.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT id, provider, model_name AS model, label, strengths, enabled, key_last4,"
                " created_at FROM model_registry WHERE user_id = :uid ORDER BY created_at"
            ),
            {"uid": user.id},
        )
    return [ModelOut(**r._mapping) for r in rows]


async def _refuse_if_full(conn: Any, user_id: uuid.UUID, body: ModelIn) -> None:
    """Refuse a new model when I already have the most allowed."""
    row = (
        await conn.execute(
            text(
                "SELECT count(*) AS saved,"
                " coalesce(bool_or(provider = :provider AND model_name = :model), false) AS dup"
                " FROM model_registry WHERE user_id = :uid"
            ),
            {"uid": user_id, "provider": body.provider, "model": body.model},
        )
    ).one()
    if row.dup:
        raise HTTPException(status.HTTP_409_CONFLICT, _DUPLICATE)
    if row.saved >= MAX_MODELS:
        raise HTTPException(status.HTTP_409_CONFLICT, _TOO_MANY)


@router.post("", status_code=status.HTTP_201_CREATED)
async def save_model(
    body: ModelIn, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> ModelOut:
    """Save a model with its key, encrypted."""
    _human(user)
    key_arn = get_settings().user_keys_kms_arn
    if key_arn is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Key storage unavailable")
    await ratelimit.enforce(
        request, f"ratelimit:models:save:{user.id}", SAVE_LIMIT, SAVE_WINDOW_SECONDS
    )
    async with request.app.state.db.connect() as conn:
        await _refuse_if_full(conn, user.id, body)
    plaintext = body.api_key.get_secret_value()
    model_id = uuid.uuid4()
    ciphertext = await kms.encrypt(
        request.app.state.kms, key_arn, plaintext, kms.context(user.id, model_id)
    )
    try:
        async with request.app.state.db.begin() as conn:
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"models:{user.id}"}
            )
            await _refuse_if_full(conn, user.id, body)
            row = (
                await conn.execute(
                    text(
                        "INSERT INTO model_registry (id, user_id, provider, model_name,"
                        " key_ciphertext, key_last4, label, strengths)"
                        " VALUES (:id, :uid, :provider, :model, :ct, :last4, :label, :strengths)"
                        " RETURNING id, provider, model_name AS model, label, strengths, enabled,"
                        " key_last4, created_at"
                    ),
                    {
                        "id": model_id,
                        "uid": user.id,
                        "provider": body.provider,
                        "model": body.model,
                        "ct": ciphertext,
                        "last4": plaintext[-4:],
                        "label": body.label,
                        "strengths": list(body.strengths),
                    },
                )
            ).one()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, _DUPLICATE) from None
    return ModelOut(**row._mapping)


@router.patch("/{model_id}")
async def update_model(
    model_id: uuid.UUID,
    body: ModelPatch,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> ModelOut:
    """Switch a model on or off, or change its tags or label."""
    _human(user)
    if body.model_dump(exclude_none=True) == {}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nothing to change")
    async with request.app.state.db.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "UPDATE model_registry SET enabled = coalesce(:enabled, enabled),"
                    " label = coalesce(:label, label),"
                    " strengths = coalesce(CAST(:strengths AS text[]), strengths)"
                    " WHERE id = :id AND user_id = :uid"
                    " RETURNING id, provider, model_name AS model, label, strengths, enabled,"
                    " key_last4, created_at"
                ),
                {
                    "enabled": body.enabled,
                    "label": body.label,
                    "strengths": None if body.strengths is None else list(body.strengths),
                    "id": model_id,
                    "uid": user.id,
                },
            )
        ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found")
    return ModelOut(**row._mapping)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    model_id: uuid.UUID, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> None:
    """Delete a saved model and its key."""
    _human(user)
    async with request.app.state.db.begin() as conn:
        deleted = await conn.execute(
            text("DELETE FROM model_registry WHERE id = :id AND user_id = :uid"),
            {"id": model_id, "uid": user.id},
        )
    if deleted.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found")
