"""Ask my AI through the orchestrator (fake orchestrator, real safety, beta database)."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from tests.conftest import beta, run_sql
from tests.test_drafts import setup  # noqa: F401

from api import memory, prompts
from api.auth import verify_token

READY = {
    "status": "ready",
    "text": "Use --platform linux/arm64 in docker buildx.",
    "reason": None,
    "plan": [{"kind": "explain", "task": "why", "model": "Thinker"}],
    "models_used": ["Coder", "Thinker"],
    "fallback_used": False,
    "trace_ids": ["11111111-1111-1111-1111-111111111111"],
}


class FakeOrchestrator:
    def __init__(self) -> None:
        """Start with no runs."""
        self.runs: list[dict[str, Any]] = []
        self.resumed: list[tuple[str, str]] = []
        self.reply: tuple[int, dict[str, Any]] = (200, READY)

    def client(self) -> httpx.AsyncClient:
        """An HTTP client that talks to this fake."""

        def handler(request: httpx.Request) -> httpx.Response:
            """Answer like the orchestrator and record the call."""
            body = json.loads(request.content)
            if request.url.path == "/runs":
                self.runs.append(body)
                code, payload = self.reply
                return httpx.Response(code, json={**payload, "run_id": str(uuid.uuid4())})
            self.resumed.append((request.url.path.split("/")[2], body["decision"]))
            return httpx.Response(204)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://orch")


@pytest.fixture
def orch(setup: tuple) -> Any:  # noqa: F811
    """A test app with a fake orchestrator."""
    client, _, thread, me = setup
    fake = FakeOrchestrator()
    client.app.state.orchestrator = fake.client()
    user_id = run_sql_user(me)
    run_sql(
        "INSERT INTO model_registry (user_id, provider, model_name, key_ciphertext, key_last4,"
        " label, strengths) VALUES (:u, 'openrouter', 'coder/x:free', :ct, 'ab12', 'Coder',"
        " '{coding}')",
        {"u": user_id, "ct": b"\x01\x02ciphertext-bytes"},
    )
    yield client, fake, thread, me, user_id
    run_sql("DELETE FROM model_registry WHERE user_id = :u", {"u": user_id}, as_owner=True)


def run_sql_user(me: dict[str, str]) -> uuid.UUID:
    """Run SQL as a test person."""
    return verify_token(me["Authorization"].split()[1]).id


def ask(client: TestClient, thread: str, me: dict[str, str], **extra: Any) -> httpx.Response:
    """Ask my AI for a draft."""
    body = {"mode": "ask_my_ai", "instruction": "answer it", "idempotency_key": uuid.uuid4().hex}
    return client.post(f"/threads/{thread}/drafts", json={**body, **extra}, headers=me)


@beta
def test_ask_my_ai_runs_the_orchestrator_and_closes_the_run(orch: Any) -> None:
    """Ask my ai runs the orchestrator and closes the run."""
    client, fake, thread, me, _ = orch
    made = ask(client, thread, me)
    assert made.status_code == 201, made.text
    out = made.json()
    assert out["text"] == READY["text"] and out["models_used"] == ["Coder", "Thinker"]
    assert out["model_label"] == "Coder + Thinker" and out["plan"][0]["kind"] == "explain"
    (sent,) = fake.runs
    assert sent["system"] == prompts.SYSTEM and sent["memory"] == []
    assert "<thread>" in sent["messages"][0]["content"]
    assert sent["models"][0]["label"] == "Coder" and sent["models"][0]["strengths"] == ["coding"]

    again = ask(client, thread, me).json()
    assert fake.resumed and fake.resumed[-1][1] == "discarded"
    assert client.post(f"/drafts/{again['id']}/approve", json={}, headers=me).status_code == 200
    assert fake.resumed[-1][1] == "approved"


@beta
def test_failures_and_memory_rules(orch: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Failures and memory rules."""
    client, fake, thread, me, _ = orch
    fake.reply = (200, {**READY, "status": "failed", "text": None, "reason": "all_models_failed"})
    busy = ask(client, thread, me)
    assert busy.status_code == 503 and "busy" in busy.json()["detail"]["message"]
    fake.reply = (500, {})
    assert ask(client, thread, me).status_code == 503
    fake.reply = (200, READY)

    now = datetime.now(UTC)
    item = memory.Item(uuid.uuid4(), "I use a Mac with arm64", None, None, now, now)

    async def found(*args: Any, **kwargs: Any) -> list[memory.Item]:
        """Memory search that finds an item."""
        return [item]

    async def load(*args: Any, **kwargs: Any) -> list[memory.Item]:
        """Memory load that returns an item."""
        return [item]

    monkeypatch.setattr(memory, "retrieve", found)
    monkeypatch.setattr(memory, "load", load)
    made = ask(client, thread, me, memory_on=True)
    assert made.status_code == 201 and made.json()["memory_used"] == [item.text]
    assert fake.runs[-1]["memory"] == [item.text]
    listed = client.get("/drafts", headers=me).json()
    assert listed[0]["memory_used"] == [item.text]

    platform = client.post(
        f"/threads/{thread}/drafts",
        json={"mode": "platform_ai", "instruction": "x", "idempotency_key": uuid.uuid4().hex,
              "memory_on": True},
        headers=me,
    )  # fmt: skip
    assert platform.status_code == 422 and platform.json()["detail"]["reason"] == "memory_platform"
    client.app.state.orchestrator = None
    off = ask(client, thread, me, memory_on=True)
    assert off.status_code == 422 and off.json()["detail"]["reason"] == "memory_unavailable"
