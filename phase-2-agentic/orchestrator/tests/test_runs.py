"""Saved runs: pause for approval, survive a restart, deleted on decide, swept when old."""

import os
import socket
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from orchestrator import main
from orchestrator.config import get_settings

RUN = {
    "request_id": "req-12345678",
    "user_id": str(uuid.uuid4()),
    "system": "You draft a reply.",
    "messages": [{"role": "user", "content": "<thread>\nWhy?\n</thread>"}],
    "models": [
        {
            "model_id": str(uuid.uuid4()),
            "provider": "openrouter",
            "model": "coder/model:free",
            "key_ciphertext": "AQJjaXBoZXJ0ZXh0LWJ5dGVz",
        }
    ],
}


def _client(app: FastAPI, text: str = "a short answer") -> TestClient:
    """A test client with a fake gateway."""
    client = TestClient(app)
    client.__enter__()

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer with fixed text."""
        return httpx.Response(200, json={"text": text, "model": "m", "trace_id": None})

    client.app.state.gateway = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(handler), base_url="http://gw"
    )
    return client


def _lifecycle(make: Any) -> None:
    """A ready run is waiting after a restart; deciding finishes and deletes it."""
    first = _client(make())
    started = first.post("/runs", json=RUN).json()
    assert started["status"] == "ready"
    run_id = started["run_id"]
    first.__exit__(None, None, None)

    second = _client(make())
    try:
        waiting = second.get(f"/runs/{run_id}")
        assert waiting.status_code == 200 and waiting.json()["text"] == "a short answer"
        assert (
            second.post(f"/runs/{run_id}/resume", json={"decision": "approved"}).status_code == 204
        )
        assert second.get(f"/runs/{run_id}").status_code == 404
        assert (
            second.post(f"/runs/{run_id}/resume", json={"decision": "approved"}).status_code == 404
        )
        bad = second.post(f"/runs/{run_id}/resume", json={"decision": "maybe"})
        assert bad.status_code == 422
    finally:
        second.__exit__(None, None, None)


def test_pause_survive_restart_and_delete_on_decide() -> None:
    """Pause survive restart and delete on decide."""
    saver = InMemorySaver()
    _lifecycle(lambda: main.create_app(saver))


def test_failed_runs_keep_nothing_and_old_runs_are_swept() -> None:
    """Failed runs keep nothing and old runs are swept."""
    saver = InMemorySaver()
    failing = _client(main.create_app(saver), text="")
    try:
        out = failing.post("/runs", json=RUN).json()
        assert out["status"] == "failed" and out["reason"] == "empty_answer"
        assert failing.get(f"/runs/{out['run_id']}").status_code == 404
    finally:
        failing.__exit__(None, None, None)

    ok = _client(main.create_app(saver))
    try:
        run_id = ok.post("/runs", json=RUN).json()["run_id"]
        portal = ok.portal
        assert portal.call(main.sweep, saver, timedelta(days=7)) == 0
        assert portal.call(main.sweep, saver, timedelta(seconds=-60)) == 1
        assert ok.get(f"/runs/{run_id}").status_code == 404
    finally:
        ok.__exit__(None, None, None)


def _port_open(port: int) -> bool:
    """Whether a local port is open."""
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture
def beta_postgres(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use the real database through the tunnel."""
    password = os.environ.get("TEST_ORCHESTRATOR_PASSWORD")
    if not (password and _port_open(15432)):
        pytest.skip("needs make db-tunnel and TEST_ORCHESTRATOR_PASSWORD")
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "15432")
    monkeypatch.setenv("POSTGRES_PASSWORD", password)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_runs_survive_a_restart_in_postgres(beta_postgres: None) -> None:
    """The real checkpointer, as the orchestrator role, in its own schema."""
    _lifecycle(lambda: main.create_app())
