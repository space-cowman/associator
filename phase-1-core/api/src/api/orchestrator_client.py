"""Ask my AI through the orchestrator."""

import base64
import logging
import uuid
from typing import Any, Literal

import httpx
from fastapi import HTTPException, Request, status
from sqlalchemy import text

from api.auth import CurrentUser

log = logging.getLogger("api.orchestrator")

FAILURES = {
    "too_long": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "The model could not answer briefly. Try again.",
    ),
    "empty_answer": (status.HTTP_503_SERVICE_UNAVAILABLE, "The model gave no answer. Try again."),
    "all_models_failed": (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Your models are busy or unavailable right now. Try again, or use Platform AI.",
    ),
}
UNAVAILABLE = "Ask my AI is unavailable right now, try again shortly"


async def models_of(request: Request, user: CurrentUser) -> list[dict[str, Any]]:
    """The person's enabled models, for the orchestrator."""
    async with request.app.state.db.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, provider, model_name, label, strengths, key_ciphertext"
                    " FROM model_registry WHERE user_id = :u AND enabled"
                    " ORDER BY created_at LIMIT 3"
                ),
                {"u": user.id},
            )
        ).all()
    if not rows:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"reason": "no_model", "message": "Save your own model first, or use Platform AI."},
        )
    return [
        {
            "model_id": str(r.id),
            "provider": r.provider,
            "model": r.model_name,
            "label": r.label,
            "strengths": list(r.strengths),
            "key_ciphertext": base64.b64encode(bytes(r.key_ciphertext)).decode(),
        }
        for r in rows
    ]


async def start(
    request: Request,
    user: CurrentUser,
    *,
    system: str,
    messages: list[dict[str, str]],
    memory: list[str],
) -> dict[str, Any]:
    """A ready run: {run_id, text, plan, models_used, trace_ids, ...}."""
    body = {
        "request_id": uuid.uuid4().hex,
        "user_id": str(user.id),
        "system": system,
        "messages": messages,
        "models": await models_of(request, user),
        "memory": memory,
        "privacy": "public",
        "trace": True,
    }
    client: httpx.AsyncClient = request.app.state.orchestrator
    try:
        response = await client.post("/runs", json=body)
        response.raise_for_status()
        run: dict[str, Any] = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    if run.get("status") != "ready":
        reason = str(run.get("reason") or "all_models_failed")
        code, message = FAILURES.get(reason, FAILURES["all_models_failed"])
        raise HTTPException(code, {"reason": reason, "message": message})
    return run


async def resume(
    request: Request, run_id: uuid.UUID | None, decision: Literal["approved", "edited", "discarded"]
) -> None:
    """Close the orchestrator's saved run."""
    client: httpx.AsyncClient | None = request.app.state.orchestrator
    if client is None or run_id is None:
        return
    try:
        await client.post(f"/runs/{run_id}/resume", json={"decision": decision})
    except httpx.HTTPError as exc:
        log.warning("run not closed (%s)", type(exc).__name__)
