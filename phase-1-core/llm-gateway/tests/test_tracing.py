"""LangSmith tracing: masked, only when allowed, never breaks a draft."""

import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway.main import create_app
from gateway.providers import Result
from gateway.tracing import Tracer

EMAIL = "ana.mehta@example.com"


class RecordingProvider:
    name, model = "fake", "fake-1"

    def __init__(self, answer: str) -> None:
        """Start with no calls and a fixed answer."""
        self.answer = answer

    async def complete(
        self, system: str, messages: list[dict[str, str]], max_tokens: int
    ) -> Result:
        """Record what the model received."""
        return Result(self.answer, 10, 5, "stop", "fake-1")


class FakeLangSmith:
    """Stands in for langsmith.Client: records runs and feedback instead of sending them."""

    def __init__(self, fail: bool = False) -> None:
        """Start with no runs."""
        self.runs: list[dict[str, Any]] = []
        self.feedback: list[dict[str, Any]] = []
        self.fail = fail

    def create_run(self, **run: Any) -> None:
        """Record a trace."""
        if self.fail:
            raise ConnectionError("LangSmith is down")
        self.runs.append(run)

    def create_feedback(self, **fb: Any) -> None:
        """Record feedback."""
        self.feedback.append(fb)


@pytest.fixture
def setup() -> Iterator[tuple[TestClient, FakeLangSmith]]:
    """A test gateway with fake LangSmith."""
    from safety.main import create_app as create_safety_app

    with TestClient(create_app()) as client:
        client.app.state.providers["fake"] = RecordingProvider(f"Mail {EMAIL} for access.")  # type: ignore[attr-defined]
        client.app.state.safety = httpx.AsyncClient(  # type: ignore[attr-defined]
            transport=httpx.ASGITransport(app=create_safety_app()), base_url="http://safety"
        )
        tracer = Tracer.__new__(Tracer)
        tracer.client, tracer.project = FakeLangSmith(), "test"  # type: ignore[assignment]
        client.app.state.tracer = tracer  # type: ignore[attr-defined]
        yield client, tracer.client  # type: ignore[misc]


def complete(client: TestClient, **extra: object) -> httpx.Response:
    """Make one traced call."""
    return client.post(
        "/complete",
        json={
            "request_id": "req-trace-0001",
            "user_id": "6db5fa3b-41a5-4106-ad2b-26bf99f902b5",
            "model": "fake",
            "messages": [{"role": "user", "content": f"My email is {EMAIL}, why does pip fail?"}],
            **extra,
        },
    )


def test_public_draft_is_traced_masked(setup: tuple[TestClient, FakeLangSmith]) -> None:
    """Public draft is traced masked."""
    client, ls = setup
    r = complete(client, trace="draft")
    assert r.status_code == 200
    assert EMAIL in r.json()["text"]
    trace_id = r.json()["trace_id"]
    assert uuid.UUID(trace_id) and len(ls.runs) == 1
    run = ls.runs[0]
    sent = str(run["inputs"]) + str(run["outputs"])
    assert EMAIL not in sent and "<EMAIL_1>" in sent
    assert "6db5fa3b" not in str(run)
    assert run["name"] == "draft" and run["extra"]["metadata"]["model"] == "fake-1"


def test_untraced_and_private_calls_send_nothing(setup: tuple[TestClient, FakeLangSmith]) -> None:
    """Untraced and private calls send nothing."""
    client, ls = setup
    assert complete(client).json()["trace_id"] is None
    assert complete(client, trace="chat_ai", privacy="private").json()["trace_id"] is None
    assert ls.runs == []


def test_feedback_scores(setup: tuple[TestClient, FakeLangSmith]) -> None:
    """Feedback scores."""
    client, ls = setup
    tid = str(uuid.uuid4())
    for decision in ("approved", "edited", "discarded"):
        assert (
            client.post("/feedback", json={"trace_id": tid, "decision": decision}).status_code
            == 204
        )
    assert [(f["score"], f["value"]) for f in ls.feedback] == [
        (1.0, "approved"),
        (0.5, "edited"),
        (0.0, "discarded"),
    ]
    assert client.post("/feedback", json={"trace_id": tid, "decision": "meh"}).status_code == 422
    body = {"trace_id": tid, "decision": "edited", "correction": f"Write to {EMAIL} first."}
    assert client.post("/feedback", json=body).status_code == 204
    assert ls.feedback[-1]["correction"] == {"answer": "Write to <EMAIL_1> first."}
    assert ls.feedback[0]["correction"] is None


def test_langsmith_down_never_breaks_a_draft(setup: tuple[TestClient, FakeLangSmith]) -> None:
    """Langsmith down never breaks a draft."""
    client, ls = setup
    ls.fail = True
    r = complete(client, trace="draft")
    assert r.status_code == 200 and r.json()["trace_id"] is None


def test_shared_private_request_traces_only_the_question(
    setup: tuple[TestClient, FakeLangSmith],
) -> None:
    """Shared private request traces only the question."""
    client, ls = setup
    r = client.post(
        "/complete",
        json={
            "request_id": "req-trace-0002",
            "user_id": "6db5fa3b-41a5-4106-ad2b-26bf99f902b5",
            "model": "fake",
            "privacy": "private",
            "names": ["ana-mehta"],
            "messages": [
                {"role": "user", "content": "<chat>@ana-mehta: secret plan</chat> question?"}
            ],
            "trace": "chat_ai",
            "trace_shared": True,
            "trace_messages": [{"role": "user", "content": "@ana-mehta asks: why does pip fail?"}],
        },
    )
    assert r.status_code == 200 and r.json()["trace_id"]
    sent = str(ls.runs[-1]["inputs"])
    assert "secret plan" not in sent
    assert "why does pip fail" in sent and "ana-mehta" not in sent
