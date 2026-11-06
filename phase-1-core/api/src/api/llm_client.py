"""The api's only way to reach a model: through the llm-gateway (rule 5)."""

import base64
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from fastapi import HTTPException, Request, status
from sqlalchemy import text

from api import metrics, ratelimit
from api.auth import CurrentUser

PLATFORM_PER_USER_DAY = 20
PLATFORM_TOTAL_DAY = 300
TOTAL_KEY = "ratelimit:platform-ai:all"
DAY = 24 * 3600

MESSAGES = {
    "upstream_busy": "This model is busy right now. Try again shortly, or use Platform AI.",
    "quota_exhausted": "Your model's quota is used up for now. Try later, or use Platform AI.",
    "invalid_key": "Your saved API key was rejected. Save a new key in your model settings.",
    "key_unavailable": "Your saved key could not be used. Save it again in your model settings.",
    "insufficient_credits": "Your model provider account has no credits left.",
    "model_unavailable": "This model is not available right now. Try another model.",
    "model_mismatch": "The provider answered with a different model, so the answer was discarded.",
    "timeout": "The model took too long to answer. Try again.",
}
DEFAULT_MESSAGE = "The model could not answer right now. Try again shortly."
YOUR_ACTION = {
    "invalid_key",
    "key_unavailable",
    "insufficient_credits",
}


@dataclass(frozen=True)
class Answer:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    finish_reason: str
    trace_id: str | None = None


def _failure(reason: str) -> HTTPException:
    """Turn a model failure into a clear error for the person."""
    if reason == "quota_exhausted":
        code = status.HTTP_429_TOO_MANY_REQUESTS
    elif reason in YOUR_ACTION:
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HTTPException(code, {"reason": reason, "message": MESSAGES.get(reason, DEFAULT_MESSAGE)})


async def complete(
    request: Request,
    user: CurrentUser,
    *,
    own_model: bool,
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int = 400,
    privacy: Literal["public", "private"] = "public",
    names: list[str] | None = None,
    trace: Literal["off", "draft", "chat_ai"] = "off",
    trace_shared: bool = False,
    trace_messages: list[dict[str, str]] | None = None,
) -> Answer:
    """Call a model through the gateway."""
    body: dict[str, Any] = {
        "request_id": uuid.uuid4().hex,
        "user_id": str(user.id),
        "system": system,
        "messages": messages,
        "max_tokens": max_tokens,
        "privacy": privacy,
        "names": names or [],
        "trace": trace,
        "trace_shared": trace_shared,
        "trace_messages": trace_messages,
    }
    if own_model:
        async with request.app.state.db.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT id, provider, model_name, key_ciphertext FROM model_registry"
                        " WHERE user_id = :uid AND enabled ORDER BY created_at LIMIT 1"
                    ),
                    {"uid": user.id},
                )
            ).one_or_none()
        if row is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"reason": "no_model", "message": "Save your own model first, or use Platform AI."},
            )
        body["model"] = "user"
        body["user_model"] = {
            "model_id": str(row.id),
            "provider": row.provider,
            "model": row.model_name,
            "key_ciphertext": base64.b64encode(bytes(row.key_ciphertext)).decode(),
        }
    else:
        await ratelimit.enforce(
            request,
            f"ratelimit:platform-ai:{user.id}",
            PLATFORM_PER_USER_DAY,
            DAY,
            "You have used today's Platform AI answers. Try again tomorrow, or use your own model.",
        )
        await ratelimit.enforce(
            request,
            TOTAL_KEY,
            PLATFORM_TOTAL_DAY,
            DAY,
            "Platform AI has reached today's limit. Try again tomorrow, or use your own model.",
        )
        body["model"] = "platform"

    model_label = body.get("user_model", {}).get("model", "platform")
    try:
        response = await request.app.state.gateway.post("/complete", json=body)
    except httpx.HTTPError:
        metrics.ai_call(own_model=own_model, privacy=privacy, model=model_label, ok=False)
        raise _failure("gateway_unreachable") from None
    if response.status_code != status.HTTP_200_OK:
        metrics.ai_call(own_model=own_model, privacy=privacy, model=model_label, ok=False)
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        if isinstance(detail, dict):
            reason = detail.get("reason") or detail.get("error")
        else:
            reason = detail
        raise _failure(str(reason or "provider_error"))
    out = response.json()
    metrics.ai_call(
        own_model=own_model,
        privacy=privacy,
        model=out["model"],
        ok=True,
        tokens_in=out["usage"]["input_tokens"],
        tokens_out=out["usage"]["output_tokens"],
        cost_usd=out["cost_usd"],
    )
    return Answer(
        text=out["text"],
        provider=out["provider"],
        model=out["model"],
        input_tokens=out["usage"]["input_tokens"],
        output_tokens=out["usage"]["output_tokens"],
        cost_usd=out["cost_usd"],
        finish_reason=out["finish_reason"],
        trace_id=out.get("trace_id"),
    )


async def feedback(
    request: Request, trace_id: object, decision: str, correction: str | None = None
) -> None:
    """Send a person's decision on a draft as AI feedback."""
    if trace_id is None:
        return
    try:
        await request.app.state.gateway.post(
            "/feedback",
            json={"trace_id": str(trace_id), "decision": decision, "correction": correction},
            timeout=5,
        )
    except httpx.HTTPError:
        pass
