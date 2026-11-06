"""Private content reaches a model only as placeholders."""

import logging
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway import privacy
from gateway.main import create_app
from gateway.providers import Result

AWS_KEY = "AKIAIOSFODNN7EXAMPLE"  # pragma: allowlist secret


class RecordingProvider:
    """Stands in for a real provider: keeps what it was sent, answers with a fixed text."""

    name, model = "fake", "fake-1"

    def __init__(self, answer: str = "Done.") -> None:
        """Start with no calls and a fixed answer."""
        self.answer = answer
        self.sent: list[list[dict[str, str]]] = []

    async def complete(
        self, system: str, messages: list[dict[str, str]], max_tokens: int
    ) -> Result:
        """Record what the model received."""
        self.sent.append(messages)
        return Result(self.answer, 10, 5, "stop", "fake-1")


@pytest.fixture
def setup() -> Iterator[tuple[TestClient, RecordingProvider]]:
    """A test gateway with a recording model."""
    from safety.main import create_app as create_safety_app

    with TestClient(create_app()) as client:
        provider = RecordingProvider()
        client.app.state.providers["fake"] = provider  # type: ignore[attr-defined]
        client.app.state.safety = httpx.AsyncClient(  # type: ignore[attr-defined]
            transport=httpx.ASGITransport(app=create_safety_app()), base_url="http://safety"
        )
        yield client, provider


def call(
    client: TestClient, text: str, privacy_level: str = "private", **extra: object
) -> httpx.Response:
    """Send a text through the gateway."""
    return client.post(
        "/complete",
        json={
            "request_id": "req-test-0001",
            "user_id": "6db5fa3b-41a5-4106-ad2b-26bf99f902b5",
            "model": "fake",
            "messages": [{"role": "user", "content": text}],
            "privacy": privacy_level,
            **extra,
        },
    )


def test_private_content_reaches_the_provider_only_as_placeholders(setup: tuple) -> None:
    """Private content reaches the provider only as placeholders."""
    client, provider = setup
    text = "Priya Sharma (priya@example.com, +91 98765 43210, aadhaar 2345 6789 0124) asked @ravi"
    assert call(client, text, names=["ravi"]).status_code == 200
    sent = provider.sent[-1][0]["content"]
    for value in ("Priya Sharma", "priya@example.com", "98765 43210", "2345 6789 0124", "ravi"):
        assert value not in sent
    assert "<EMAIL_1>" in sent and "<USER_1>" in sent


def test_answer_is_restored_for_the_chat(setup: tuple) -> None:
    """Answer is restored for the chat."""
    client, provider = setup
    provider.answer = "Send the invoice to <EMAIL_1>."
    out = call(client, "invoice for priya@example.com please")
    assert out.json()["text"] == "Send the invoice to priya@example.com."


def test_secrets_never_reach_the_provider_or_come_back(setup: tuple) -> None:
    """Secrets never reach the provider or come back."""
    client, provider = setup
    provider.answer = "Use [SECRET REMOVED] again."
    out = call(client, f"deploy with {AWS_KEY}")
    assert AWS_KEY not in provider.sent[-1][0]["content"]
    assert AWS_KEY not in out.json()["text"]


def test_public_content_is_unchanged(setup: tuple) -> None:
    """Public content is unchanged."""
    client, provider = setup
    call(client, "contact priya@example.com", privacy_level="public")
    assert provider.sent[-1][0]["content"] == "contact priya@example.com"


def test_no_masking_means_no_model_call(setup: tuple) -> None:
    """No masking means no model call."""
    client, provider = setup

    def down(request: httpx.Request) -> httpx.Response:
        """Fail like a safety service that is down."""
        raise httpx.ConnectError("safety is down")

    client.app.state.safety = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(down), base_url="http://safety"
    )
    out = call(client, "mail priya@example.com")
    assert out.status_code == 503 and out.json()["detail"] == "privacy_unavailable"
    assert provider.sent == []


def test_nothing_sensitive_is_logged(setup: tuple, caplog: pytest.LogCaptureFixture) -> None:
    """Nothing sensitive is logged."""
    client, _ = setup
    with caplog.at_level(logging.DEBUG):
        call(client, "mail priya@example.com")
    assert "priya@example.com" not in caplog.text and "<EMAIL_1>" not in caplog.text


def test_restore_touches_only_our_placeholders_and_runs_once() -> None:
    """Restore touches only our placeholders and runs once."""
    table = {"<EMAIL_1>": "a@example.com", "<PERSON_1>": "<PERSON_2>"}
    out = privacy.restore("<EMAIL_1>, <EMAIL_9>, <PERSON_1>", table)
    assert out == "a@example.com, <EMAIL_9>, <PERSON_2>"


@pytest.mark.parametrize("override", [{"privacy": "secret"}, {"names": ["Bad Name!"]}])
def test_bad_privacy_requests_are_422(setup: tuple, override: dict) -> None:
    """Bad privacy requests are 422."""
    client, _ = setup
    assert call(client, "hi", **override).status_code == 422
