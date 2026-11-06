"""Every model call goes through the llm-gateway."""

import uuid
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from orchestrator.contract import ModelRef, RunIn


@dataclass(frozen=True)
class Reply:
    text: str
    model: str
    trace_id: str | None


class GatewayError(Exception):
    """A failed gateway call with its cause."""

    def __init__(self, reason: str, status_code: int = 0) -> None:
        """Keep the cause and status of a failure."""
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


async def complete(
    client: httpx.AsyncClient,
    run: RunIn,
    model: ModelRef | None,
    *,
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    trace: Literal["off", "draft"] = "off",
    trace_messages: list[dict[str, str]] | None = None,
) -> Reply:
    """Call a model through the gateway."""
    body: dict[str, Any] = {
        "request_id": uuid.uuid4().hex,
        "user_id": str(run.user_id),
        "model": "platform" if model is None else "user",
        "system": system,
        "messages": messages,
        "max_tokens": max_tokens,
        "privacy": run.privacy,
        "names": run.names,
        "trace": trace if run.trace else "off",
        "trace_messages": trace_messages,
    }
    if model is not None:
        body["user_model"] = {
            "model_id": str(model.model_id),
            "provider": model.provider,
            "model": model.model,
            "key_ciphertext": model.key_ciphertext,
        }
    try:
        response = await client.post("/complete", json=body)
    except httpx.HTTPError:
        raise GatewayError("gateway_unreachable") from None
    if response.status_code != 200:
        raise GatewayError(_reason(response), response.status_code)
    out = response.json()
    return Reply(text=str(out["text"]), model=str(out["model"]), trace_id=out.get("trace_id"))


def _reason(response: httpx.Response) -> str:
    """Read the cause from a gateway error."""
    try:
        detail = response.json().get("detail")
    except ValueError:
        return "gateway_error"
    if isinstance(detail, dict):
        return str(detail.get("reason") or detail.get("error") or "gateway_error")
    return str(detail or "gateway_error")
