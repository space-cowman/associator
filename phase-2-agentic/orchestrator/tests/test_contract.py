"""The api -> orchestrator contract, the gateway client, and tracing kept off."""

import json
import os
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from orchestrator import gateway
from orchestrator.contract import ModelRef, RunIn
from orchestrator.main import create_app

MODEL = {
    "model_id": str(uuid.uuid4()),
    "provider": "openrouter",
    "model": "google/gemma-4-31b-it:free",
    "label": "Gemma",
    "strengths": ["coding"],
    "key_ciphertext": "AQJjaXBoZXJ0ZXh0LWJ5dGVz",
}
RUN = {
    "request_id": "req-12345678",
    "user_id": str(uuid.uuid4()),
    "system": "You draft a reply.",
    "messages": [{"role": "user", "content": "<thread>\nWhy does my pod restart?\n</thread>"}],
    "models": [MODEL],
}


def test_langgraph_tracing_is_off() -> None:
    """Langgraph tracing is off."""
    import orchestrator.config  # noqa: F401

    for flag in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
        assert os.environ[flag] == "false"


def test_contract_limits() -> None:
    """Contract limits."""
    assert RunIn.model_validate(RUN).models[0].name == "Gemma"
    for bad in (
        {"models": []},
        {"models": [MODEL] * 4},
        {"memory": ["x"] * 6},
        {"memory": ["x" * 301]},
        {"names": ["Not A Handle"]},
        {"messages": []},
        {"messages": [{"role": "system", "content": "x"}]},
        {"extra": "field"},
        {"models": [{**MODEL, "strengths": ["fast"]}]},
    ):
        with pytest.raises(ValidationError):
            RunIn.model_validate({**RUN, **bad})
    assert ModelRef.model_validate({**MODEL, "label": None}).name == MODEL["model"]


def test_service_is_up_and_validates_runs() -> None:
    """Service is up and validates runs."""
    with TestClient(create_app()) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.post("/runs", json={**RUN, "models": []}).status_code == 422
        assert client.get("/docs").status_code == 404


def _gateway(code: int, payload: dict[str, Any], sent: list[dict[str, Any]]) -> httpx.AsyncClient:
    """A fake gateway with a fixed reply."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer and record the request."""
        sent.append(json.loads(request.content))
        return httpx.Response(code, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://gw")


async def _call(client: httpx.AsyncClient, run: RunIn, model: ModelRef | None) -> gateway.Reply:
    """Call a model through the fake."""
    return await gateway.complete(
        client, run, model, system="s", messages=[{"role": "user", "content": "q"}], max_tokens=50
    )


@pytest.mark.anyio
async def test_gateway_client_sends_the_persons_model_and_maps_errors() -> None:
    """Gateway client sends the persons model and maps errors."""
    run = RunIn.model_validate({**RUN, "privacy": "private", "names": ["ana-1"], "trace": False})
    sent: list[dict[str, Any]] = []
    ok = _gateway(200, {"text": "hi", "model": "gemma", "trace_id": None}, sent)
    reply = await _call(ok, run, run.models[0])
    assert reply.text == "hi"
    body = sent[-1]
    assert (
        body["model"] == "user" and body["user_model"]["key_ciphertext"] == MODEL["key_ciphertext"]
    )
    assert body["privacy"] == "private" and body["names"] == ["ana-1"] and body["trace"] == "off"
    await _call(ok, run, None)
    assert sent[-1]["model"] == "platform" and "user_model" not in sent[-1]

    busy = _gateway(429, {"detail": {"error": "rate_limited", "reason": "quota_exhausted"}}, sent)
    with pytest.raises(gateway.GatewayError) as exc:
        await _call(busy, run, run.models[0])
    assert exc.value.reason == "quota_exhausted" and exc.value.status_code == 429
