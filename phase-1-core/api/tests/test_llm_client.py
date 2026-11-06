import json
import uuid
from collections.abc import Iterator
from typing import Annotated, Any

import httpx
import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient
from tests.conftest import auth_header, beta, run_sql

from api import llm_client
from api.auth import CurrentUser, current_user
from api.main import create_app

OK_REPLY = {
    "text": "an answer",
    "provider": "groq",
    "model": "openai/gpt-oss-120b",
    "usage": {"input_tokens": 9, "output_tokens": 3},
    "cost_usd": 0.0,
    "duration_ms": 5,
    "finish_reason": "stop",
}


class FakeGateway:
    """Stands in for the llm-gateway and records what the api sent it."""

    def __init__(self) -> None:
        """Start with no calls."""
        self.sent: list[dict[str, Any]] = []
        self.reply: tuple[int, dict[str, Any]] = (200, OK_REPLY)

    def client(self) -> httpx.AsyncClient:
        """An HTTP client that talks to this fake."""

        def handler(request: httpx.Request) -> httpx.Response:
            """Answer like the gateway and record the call."""
            self.sent.append(json.loads(request.content))
            code, payload = self.reply
            return httpx.Response(code, json=payload)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://gw")


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, FakeGateway]]:
    """A test app with a fake gateway."""
    monkeypatch.setattr(llm_client, "TOTAL_KEY", f"ratelimit:platform-ai:test-{uuid.uuid4().hex}")
    app = create_app()

    @app.post("/test-llm")
    async def call_llm(
        request: Request, user: Annotated[CurrentUser, Depends(current_user)], own: bool = False
    ) -> dict[str, Any]:
        """Call the model through the client."""
        answer = await llm_client.complete(
            request,
            user,
            own_model=own,
            system="Answer briefly.",
            messages=[{"role": "user", "content": "What is Postgres?"}],
        )
        return answer.__dict__

    gateway = FakeGateway()
    with TestClient(app) as client:
        client.app.state.gateway = gateway.client()  # type: ignore[attr-defined]
        yield client, gateway
        client.portal.call(client.app.state.redis.delete, llm_client.TOTAL_KEY)


@beta
def test_platform_ai_calls_and_daily_caps(
    setup: tuple[TestClient, FakeGateway], beta_user: tuple[uuid.UUID, str]
) -> None:
    """Platform ai calls and daily caps."""
    client, gateway = setup
    user_id, handle = beta_user
    me = auth_header(user_id, handle)
    per_user = f"ratelimit:platform-ai:{user_id}"
    try:
        r = client.post("/test-llm", headers=me)
        assert r.status_code == 200 and r.json()["text"] == "an answer"
        assert gateway.sent[-1]["model"] == "platform" and "user_model" not in gateway.sent[-1]

        client.portal.call(client.app.state.redis.set, per_user, llm_client.PLATFORM_PER_USER_DAY)
        calls = len(gateway.sent)
        capped = client.post("/test-llm", headers=me)
        assert capped.status_code == 429 and "today's Platform AI" in capped.json()["detail"]
        assert len(gateway.sent) == calls

        client.portal.call(client.app.state.redis.delete, per_user)
        client.portal.call(
            client.app.state.redis.set, llm_client.TOTAL_KEY, llm_client.PLATFORM_TOTAL_DAY
        )
        total = client.post("/test-llm", headers=me)
        assert total.status_code == 429 and "Platform AI has reached" in total.json()["detail"]
    finally:
        client.portal.call(client.app.state.redis.delete, per_user)


@beta
def test_own_model_sends_ciphertext_and_explains_failures(
    setup: tuple[TestClient, FakeGateway], beta_user: tuple[uuid.UUID, str]
) -> None:
    """Own model sends ciphertext and explains failures."""
    client, gateway = setup
    user_id, handle = beta_user
    me = auth_header(user_id, handle)

    no_model = client.post("/test-llm?own=true", headers=me)
    assert no_model.status_code == 409 and no_model.json()["detail"]["reason"] == "no_model"

    model_id = uuid.uuid4()
    run_sql(
        "INSERT INTO model_registry (id, user_id, provider, model_name, key_ciphertext, key_last4)"
        " VALUES (:id, :u, 'openrouter', 'nvidia/nemotron-3.5-lightning:free', :ct, 'ab12')",
        {"id": model_id, "u": user_id, "ct": b"\x01\x02ciphertext-bytes"},
    )
    try:
        ok = client.post("/test-llm?own=true", headers=me)
        assert ok.status_code == 200
        sent = gateway.sent[-1]
        assert sent["model"] == "user" and sent["user_model"]["model_id"] == str(model_id)
        assert sent["user_model"]["key_ciphertext"] == "AQJjaXBoZXJ0ZXh0LWJ5dGVz"

        cases = {
            ("rate_limited", "upstream_busy", 429): (503, "busy right now"),
            ("rate_limited", "quota_exhausted", 429): (429, "quota is used up"),
            ("provider_error", "invalid_key", 502): (409, "rejected"),
            ("provider_error", "provider_error", 502): (503, "could not answer"),
        }
        for (error, reason, code), (expected, words) in cases.items():
            gateway.reply = (code, {"detail": {"error": error, "reason": reason, "upstream": "X"}})
            r = client.post("/test-llm?own=true", headers=me)
            assert r.status_code == expected and words in r.json()["detail"]["message"], reason
        gateway.reply = (403, {"detail": "key_unavailable"})
        assert client.post("/test-llm?own=true", headers=me).status_code == 409

        gateway.reply = (200, OK_REPLY)
        newer = uuid.uuid4()
        run_sql(
            "INSERT INTO model_registry (id, user_id, provider, model_name, key_ciphertext,"
            " key_last4, created_at) VALUES (:id, :u, 'openrouter', 'qwen/qwen3-coder:free',"
            " :ct, 'cd34', now() + interval '1 second')",
            {"id": newer, "u": user_id, "ct": b"other"},
        )
        client.post("/test-llm?own=true", headers=me)
        assert gateway.sent[-1]["user_model"]["model_id"] == str(model_id)
        run_sql("UPDATE model_registry SET enabled = false WHERE id = :id", {"id": model_id})
        client.post("/test-llm?own=true", headers=me)
        assert gateway.sent[-1]["user_model"]["model_id"] == str(newer)
    finally:
        run_sql("DELETE FROM model_registry WHERE user_id = :u", {"u": user_id}, as_owner=True)


@beta
def test_gateway_unreachable_is_503(
    setup: tuple[TestClient, FakeGateway], beta_user: tuple[uuid.UUID, str]
) -> None:
    """Gateway unreachable is 503."""
    client, _ = setup
    user_id, handle = beta_user
    client.app.state.gateway = httpx.AsyncClient(base_url="http://127.0.0.1:1")  # type: ignore[attr-defined]
    try:
        r = client.post("/test-llm", headers=auth_header(user_id, handle))
        assert r.status_code == 503 and r.json()["detail"]["reason"] == "gateway_unreachable"
    finally:
        client.portal.call(client.app.state.redis.delete, f"ratelimit:platform-ai:{user_id}")


def test_business_counters_are_safe_without_telemetry() -> None:
    """Telemetry is off in tests: the counters must be harmless no-ops, never errors."""
    from api import metrics

    metrics.draft_decided("platform_ai", "approved")
    metrics.ai_call(
        own_model=False, privacy="public", model="m", ok=True, tokens_in=3, cost_usd=0.1
    )
    metrics.safety_finding("secret", "AWS Access Key", "blocked")
    metrics.chat_event("message")
    metrics.socket_opened()
    metrics.socket_closed()
